"""Bounded idempotency guard for caller-declared shell operation keys."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class DedupeRecord:
    key: str
    fingerprint: str
    created_at: float
    expires_at: float
    state: str = "reserved"
    receipt_id: str | None = None


class DedupeConflict(RuntimeError):
    pass


class DedupeRegistry:
    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        max_records: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0 or max_records <= 0:
            raise ValueError("dedupe bounds must be positive")
        self.ttl_seconds = ttl_seconds
        self.max_records = max_records
        self._clock = clock
        self._records: dict[str, DedupeRecord] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = self._clock()
        expired = [key for key, record in self._records.items() if record.expires_at <= now]
        for key in expired:
            del self._records[key]

    def reserve(self, key: str, fingerprint: str) -> DedupeRecord:
        if not key or len(key) > 256 or not fingerprint:
            raise ValueError("idempotency key and fingerprint are required")
        with self._lock:
            self._prune()
            existing = self._records.get(key)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise DedupeConflict("idempotency key was reused for a different command fingerprint")
                return existing
            if len(self._records) >= self.max_records:
                raise DedupeConflict("dedupe registry capacity exhausted")
            now = self._clock()
            record = DedupeRecord(key, fingerprint, now, now + self.ttl_seconds)
            self._records[key] = record
            return record

    def complete(self, key: str, fingerprint: str, receipt_id: str) -> DedupeRecord:
        with self._lock:
            self._prune()
            existing = self._records.get(key)
            if existing is None or existing.fingerprint != fingerprint:
                raise DedupeConflict("no matching idempotency reservation exists")
            completed = DedupeRecord(
                existing.key,
                existing.fingerprint,
                existing.created_at,
                existing.expires_at,
                state="completed",
                receipt_id=receipt_id,
            )
            self._records[key] = completed
            return completed

    def get(self, key: str) -> DedupeRecord | None:
        with self._lock:
            self._prune()
            return self._records.get(key)

    def snapshot(self) -> tuple[DedupeRecord, ...]:
        with self._lock:
            self._prune()
            return tuple(sorted(self._records.values(), key=lambda record: record.created_at))
