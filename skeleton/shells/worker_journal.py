"""Tamper-evident append-only journal for worker lifecycle events."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import threading
import time
from types import MappingProxyType
from typing import Callable, Mapping


def _canonical(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class WorkerJournalEvent:
    sequence: int
    observed_at: float
    worker_id: str
    generation: int
    kind: str
    detail: Mapping[str, object] = field(default_factory=dict)
    previous_digest: str = ""
    digest: str = ""

    def __post_init__(self) -> None:
        if self.sequence <= 0:
            raise ValueError("journal sequence must be positive")
        if self.observed_at < 0:
            raise ValueError("observed_at may not be negative")
        if not self.worker_id or len(self.worker_id) > 128:
            raise ValueError("invalid worker_id")
        if self.generation <= 0:
            raise ValueError("generation must be positive")
        if not self.kind or len(self.kind) > 128:
            raise ValueError("invalid journal event kind")
        if len(self.detail) > 64:
            raise ValueError("journal detail has too many fields")
        object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "observed_at": self.observed_at,
            "worker_id": self.worker_id,
            "generation": self.generation,
            "kind": self.kind,
            "detail": dict(self.detail),
            "previous_digest": self.previous_digest,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.unsigned_dict()
        payload["digest"] = self.digest
        return payload

    def expected_digest(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()


@dataclass(frozen=True)
class JournalVerification:
    valid: bool
    checked: int
    first_invalid_sequence: int | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "checked": self.checked,
            "first_invalid_sequence": self.first_invalid_sequence,
            "reason": self.reason,
        }


class WorkerJournal:
    """In-memory hash chain suitable for audit/export adapters."""

    def __init__(
        self,
        *,
        max_events: int = 100_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        self.max_events = max_events
        self._clock = clock
        self._events: list[WorkerJournalEvent] = []
        self._lock = threading.RLock()

    def append(
        self,
        *,
        worker_id: str,
        generation: int,
        kind: str,
        detail: Mapping[str, object] | None = None,
    ) -> WorkerJournalEvent:
        with self._lock:
            if len(self._events) >= self.max_events:
                raise RuntimeError("worker journal capacity exhausted")
            sequence = len(self._events) + 1
            previous = "" if not self._events else self._events[-1].digest
            provisional = WorkerJournalEvent(
                sequence=sequence,
                observed_at=self._clock(),
                worker_id=worker_id,
                generation=generation,
                kind=kind,
                detail=detail or {},
                previous_digest=previous,
            )
            event = WorkerJournalEvent(
                sequence=provisional.sequence,
                observed_at=provisional.observed_at,
                worker_id=provisional.worker_id,
                generation=provisional.generation,
                kind=provisional.kind,
                detail=provisional.detail,
                previous_digest=provisional.previous_digest,
                digest=provisional.expected_digest(),
            )
            self._events.append(event)
            return event

    def verify(self) -> JournalVerification:
        with self._lock:
            previous = ""
            for index, event in enumerate(self._events, start=1):
                if event.sequence != index:
                    return JournalVerification(False, index - 1, event.sequence, "sequence discontinuity")
                if event.previous_digest != previous:
                    return JournalVerification(False, index - 1, event.sequence, "previous digest mismatch")
                if event.digest != event.expected_digest():
                    return JournalVerification(False, index - 1, event.sequence, "event digest mismatch")
                previous = event.digest
            return JournalVerification(True, len(self._events))

    def events(
        self,
        *,
        worker_id: str | None = None,
        kind: str | None = None,
        after_sequence: int = 0,
        limit: int | None = None,
    ) -> tuple[WorkerJournalEvent, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence may not be negative")
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        with self._lock:
            filtered = [
                event
                for event in self._events
                if event.sequence > after_sequence
                and (worker_id is None or event.worker_id == worker_id)
                and (kind is None or event.kind == kind)
            ]
            if limit is not None:
                filtered = filtered[:limit]
            return tuple(filtered)

    def tail(self, count: int = 100) -> tuple[WorkerJournalEvent, ...]:
        if count <= 0:
            raise ValueError("count must be positive")
        with self._lock:
            return tuple(self._events[-count:])

    @property
    def head_digest(self) -> str:
        with self._lock:
            return "" if not self._events else self._events[-1].digest

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
