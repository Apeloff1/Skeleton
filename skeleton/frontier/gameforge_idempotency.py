"""Provider-neutral idempotency contract inspired by GameForge service invariants."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Generic, Hashable, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class IdempotencyStats:
    accepted: int
    duplicates: int
    evicted: int


class IdempotencyWindow(Generic[T]):
    """Bounded first-writer-wins window for retry-safe command results."""

    def __init__(self, capacity: int = 1024) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._values: Dict[Hashable, T] = {}
        self._accepted = 0
        self._duplicates = 0
        self._evicted = 0

    def record(self, key: Hashable, value: T) -> tuple[bool, T]:
        existing = self._values.get(key)
        if existing is not None:
            self._duplicates += 1
            return False, existing
        if len(self._values) >= self._capacity:
            oldest = next(iter(self._values))
            del self._values[oldest]
            self._evicted += 1
        self._values[key] = value
        self._accepted += 1
        return True, value

    def lookup(self, key: Hashable) -> Optional[T]:
        return self._values.get(key)

    def stats(self) -> IdempotencyStats:
        return IdempotencyStats(self._accepted, self._duplicates, self._evicted)

    def __len__(self) -> int:
        return len(self._values)
