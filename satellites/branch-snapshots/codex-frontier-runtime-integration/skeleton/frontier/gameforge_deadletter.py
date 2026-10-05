"""Bounded dead-letter queue for fail-safe rejection handling."""

from collections import deque
from threading import Lock


class DeadLetterQueue:
    def __init__(self, capacity: int = 256):
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self._q = deque()
        self._cap = capacity
        self._lock = Lock()

    def push(self, item) -> bool:
        with self._lock:
            if len(self._q) >= self._cap:
                return False
            self._q.append(item)
            return True

    def drain(self) -> list:
        with self._lock:
            items = list(self._q)
            self._q.clear()
            return items

    @property
    def capacity(self) -> int:
        return self._cap

    def __len__(self):
        with self._lock:
            return len(self._q)
