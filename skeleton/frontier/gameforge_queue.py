"""Bounded FIFO queue with explicit backpressure."""
from collections import deque


class BoundedQueue:
    def __init__(self, capacity):
        if not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._items = deque()

    @property
    def remaining(self):
        return self.capacity - len(self._items)

    @property
    def full(self):
        return len(self._items) >= self.capacity

    def push(self, item):
        if self.full:
            return False
        self._items.append(item)
        return True

    def pop(self):
        return self._items.popleft() if self._items else None

    def peek(self):
        return self._items[0] if self._items else None

    def __len__(self):
        return len(self._items)
