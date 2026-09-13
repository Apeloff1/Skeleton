"""Bounded outbox contract for durable handoff without a persistence dependency."""
from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


class BoundedOutbox(Generic[T]):
    def __init__(self, capacity: int = 1024) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self._q = deque()
        self._cap = capacity
        self._lock = Lock()

    def append(self, item: T) -> bool:
        with self._lock:
            if len(self._q) >= self._cap:
                return False
            self._q.append(item)
            return True

    def pop(self) -> T | None:
        with self._lock:
            return self._q.popleft() if self._q else None

    def peek(self) -> T | None:
        with self._lock:
            return self._q[0] if self._q else None

    @property
    def capacity(self) -> int:
        return self._cap

    @property
    def remaining(self) -> int:
        with self._lock:
            return self._cap - len(self._q)

    def __len__(self) -> int:
        with self._lock:
            return len(self._q)
