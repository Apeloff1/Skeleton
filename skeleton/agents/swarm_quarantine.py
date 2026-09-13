"""Worker quarantine state for isolating unhealthy executors without deleting them."""
from __future__ import annotations
from dataclasses import dataclass
from time import monotonic
from typing import Callable

@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    worker_id: str
    reason: str
    since: float
    until: float | None

class QuarantineController:
    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._records: dict[str, QuarantineRecord] = {}
    def quarantine(self, worker_id: str, *, reason: str, seconds: float | None = None) -> QuarantineRecord:
        worker_id = worker_id.strip()
        if not worker_id: raise ValueError("worker_id must not be empty")
        if seconds is not None and seconds <= 0: raise ValueError("seconds must be positive")
        now = self._clock(); rec = QuarantineRecord(worker_id, reason[:2000], now, None if seconds is None else now + seconds)
        self._records[worker_id] = rec; return rec
    def release(self, worker_id: str) -> bool:
        return self._records.pop(worker_id.strip(), None) is not None
    def is_quarantined(self, worker_id: str) -> bool:
        worker_id = worker_id.strip(); rec = self._records.get(worker_id)
        if rec is None: return False
        if rec.until is not None and rec.until <= self._clock():
            self._records.pop(worker_id, None); return False
        return True
    def records(self) -> tuple[QuarantineRecord, ...]:
        for worker_id in tuple(self._records): self.is_quarantined(worker_id)
        return tuple(sorted(self._records.values(), key=lambda r: r.worker_id))
