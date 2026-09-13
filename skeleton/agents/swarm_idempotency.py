"""Bounded idempotency primitives for externally submitted swarm work."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock
from typing import Mapping


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    key: str
    task_id: str
    fingerprint: str


class IdempotencyConflict(ValueError):
    pass


class IdempotencyRegistry:
    def __init__(self, *, max_entries: int = 100_000) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._records: OrderedDict[str, IdempotencyRecord] = OrderedDict()
        self._lock = RLock()

    @staticmethod
    def fingerprint(payload: Mapping[str, object]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return sha256(encoded).hexdigest()

    def resolve(self, key: str, task_id: str, payload: Mapping[str, object]) -> IdempotencyRecord:
        key = key.strip()
        if not key:
            raise ValueError("idempotency key must not be empty")
        fingerprint = self.fingerprint(payload)
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                self._records.move_to_end(key)
                if existing.task_id != task_id or existing.fingerprint != fingerprint:
                    raise IdempotencyConflict(f"idempotency key reused with different request: {key}")
                return existing
            record = IdempotencyRecord(key, task_id, fingerprint)
            self._records[key] = record
            while len(self._records) > self.max_entries:
                self._records.popitem(last=False)
            return record

    def get(self, key: str) -> IdempotencyRecord | None:
        with self._lock:
            return self._records.get(key)

    def snapshot(self) -> tuple[IdempotencyRecord, ...]:
        with self._lock:
            return tuple(self._records.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)
