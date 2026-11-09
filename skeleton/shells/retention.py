"""Bounded retention store for classified shell output metadata and bytes."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from skeleton.shells.output_policy import ClassifiedOutput, OutputClass


@dataclass(frozen=True)
class RetainedOutput:
    key: str
    classification: OutputClass
    payload: bytes
    digest: str
    original_bytes: int
    stored_at: float
    expires_at: float

    @property
    def expired(self) -> bool:
        return False


class OutputRetentionStore:
    def __init__(
        self,
        *,
        max_items: int = 10000,
        max_total_bytes: int = 64 * 1024 * 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_items <= 0 or max_total_bytes < 0:
            raise ValueError("invalid retention bounds")
        self.max_items = max_items
        self.max_total_bytes = max_total_bytes
        self._clock = clock
        self._items: dict[str, RetainedOutput] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = self._clock()
        for key in [key for key, value in self._items.items() if value.expires_at <= now]:
            del self._items[key]

    def _total_bytes(self) -> int:
        return sum(len(item.payload) for item in self._items.values())

    def put(
        self,
        key: str,
        output: ClassifiedOutput,
        *,
        retention_seconds: float,
    ) -> RetainedOutput:
        if not key or len(key) > 256:
            raise ValueError("invalid retention key")
        if retention_seconds < 0:
            raise ValueError("retention_seconds may not be negative")
        with self._lock:
            self._prune()
            if key not in self._items and len(self._items) >= self.max_items:
                raise RuntimeError("retention item capacity exhausted")
            existing = self._items.get(key)
            existing_bytes = 0 if existing is None else len(existing.payload)
            projected = self._total_bytes() - existing_bytes + len(output.retained)
            if projected > self.max_total_bytes:
                raise RuntimeError("retention byte capacity exhausted")
            now = self._clock()
            retained = RetainedOutput(
                key,
                output.classification,
                bytes(output.retained),
                output.digest,
                output.original_bytes,
                now,
                now + retention_seconds,
            )
            self._items[key] = retained
            return retained

    def get(self, key: str) -> RetainedOutput | None:
        with self._lock:
            self._prune()
            return self._items.get(key)

    def remove(self, key: str) -> bool:
        with self._lock:
            return self._items.pop(key, None) is not None

    def prune(self) -> int:
        with self._lock:
            before = len(self._items)
            self._prune()
            return before - len(self._items)

    def snapshot(self) -> tuple[RetainedOutput, ...]:
        with self._lock:
            self._prune()
            return tuple(self._items[key] for key in sorted(self._items))
