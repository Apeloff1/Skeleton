"""Provider-neutral idempotency contract inspired by GameForge service invariants."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, Hashable, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class IdempotencyStats:
    accepted: int
    duplicates: int
    evicted: int


class IdempotencyWindow(Generic[T]):
    """Bounded first-writer-wins window for retry-safe command results."""

    def __init__(self, capacity: int = 1024) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._values: OrderedDict[Hashable, T] = OrderedDict()
        self._accepted = 0
        self._duplicates = 0
        self._evicted = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def record(self, key: Hashable, value: T) -> tuple[bool, T]:
        if key in self._values:
            self._duplicates += 1
            return False, self._values[key]
        if len(self._values) >= self._capacity:
            self._values.popitem(last=False)
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
