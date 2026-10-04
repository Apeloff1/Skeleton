"""Worker quarantine state for isolating unhealthy executors without deleting them."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from time import monotonic
from typing import Callable, Mapping

@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    worker_id: str
    reason: str
    since: float
    until: float | None

class QuarantineController:
    STATE_VERSION = 1

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        self._records: dict[str, QuarantineRecord] = {}

    def _now(self) -> float:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError("quarantine clock must return a finite number")
        value = float(value)
        if not isfinite(value):
            raise RuntimeError("quarantine clock must return a finite number")
        return value
    def quarantine(self, worker_id: str, *, reason: str, seconds: float | None = None) -> QuarantineRecord:
        worker_id = worker_id.strip()
        if not worker_id: raise ValueError("worker_id must not be empty")
        if seconds is not None and seconds <= 0: raise ValueError("seconds must be positive")
        now = self._now(); rec = QuarantineRecord(worker_id, reason[:2000], now, None if seconds is None else now + seconds)
        self._records[worker_id] = rec; return rec
    def release(self, worker_id: str) -> bool:
        return self._records.pop(worker_id.strip(), None) is not None
    def is_quarantined(self, worker_id: str) -> bool:
        worker_id = worker_id.strip(); rec = self._records.get(worker_id)
        if rec is None: return False
        if rec.until is not None and rec.until <= self._now():
            self._records.pop(worker_id, None); return False
        return True
    def records(self) -> tuple[QuarantineRecord, ...]:
        for worker_id in tuple(self._records): self.is_quarantined(worker_id)
        return tuple(sorted(self._records.values(), key=lambda r: r.worker_id))

    def export_state(self) -> dict[str, object]:
        """Serialize quarantine state using restart-portable relative durations."""
        now = self._now()
        records: list[dict[str, object]] = []
        for record in self.records():
            remaining = None if record.until is None else max(0.0, record.until - now)
            if remaining == 0.0:
                continue
            records.append({
                "worker_id": record.worker_id,
                "reason": record.reason,
                "elapsed_seconds": max(0.0, now - record.since),
                "remaining_seconds": remaining,
            })
        return {"version": self.STATE_VERSION, "records": records}

    @classmethod
    def from_state(
        cls,
        state: Mapping[str, object],
        *,
        clock: Callable[[], float] = monotonic,
    ) -> "QuarantineController":
        if not isinstance(state, Mapping) or set(state) != {"version", "records"}:
            raise ValueError("invalid quarantine state envelope")
        if state.get("version") != cls.STATE_VERSION:
            raise ValueError("unsupported quarantine state version")
        raw_records = state.get("records")
        if not isinstance(raw_records, list):
            raise ValueError("quarantine records must be a list")
        controller = cls(clock=clock)
        now = controller._now()
        seen: set[str] = set()
        for raw in raw_records:
            if not isinstance(raw, Mapping) or set(raw) != {
                "worker_id", "reason", "elapsed_seconds", "remaining_seconds"
            }:
                raise ValueError("invalid quarantine record")
            worker_id = raw.get("worker_id")
            reason = raw.get("reason")
            if not isinstance(worker_id, str) or not worker_id.strip():
                raise ValueError("quarantine worker_id must not be empty")
            worker_id = worker_id.strip()
            if worker_id in seen:
                raise ValueError("duplicate quarantine worker_id")
            seen.add(worker_id)
            if not isinstance(reason, str):
                raise ValueError("quarantine reason must be text")
            elapsed_raw = raw.get("elapsed_seconds")
            remaining_raw = raw.get("remaining_seconds")
            if isinstance(elapsed_raw, bool) or not isinstance(elapsed_raw, (int, float)):
                raise ValueError("quarantine elapsed_seconds must be finite")
            elapsed = float(elapsed_raw)
            if not isfinite(elapsed) or elapsed < 0:
                raise ValueError("quarantine elapsed_seconds must be finite")
            if remaining_raw is None:
                until = None
            else:
                if isinstance(remaining_raw, bool) or not isinstance(remaining_raw, (int, float)):
                    raise ValueError("quarantine remaining_seconds must be positive")
                remaining = float(remaining_raw)
                if not isfinite(remaining) or remaining <= 0:
                    raise ValueError("quarantine remaining_seconds must be positive")
                until = now + remaining
            controller._records[worker_id] = QuarantineRecord(
                worker_id=worker_id,
                reason=reason[:2000],
                since=now - elapsed,
                until=until,
            )
        return controller

