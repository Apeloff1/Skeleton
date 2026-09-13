"""Bounded sliding-window counter."""
from collections import deque


class SlidingWindow:
    def __init__(self, capacity: int):
        if not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("capacity must be positive")
        self._q = deque(maxlen=capacity)
        self._cap = capacity

    @property
    def capacity(self) -> int:
        return self._cap

    @property
    def full(self) -> bool:
        return len(self._q) >= self._cap

    def add(self, value) -> None:
        self._q.append(value)

    def values(self) -> tuple:
        return tuple(self._q)

    def clear(self) -> None:
        self._q.clear()

    def __len__(self):
        return len(self._q)
