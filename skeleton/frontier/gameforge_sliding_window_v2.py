"""Deterministic bounded sliding window v2."""
from collections import deque

class SlidingWindowV2:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._items = deque(maxlen=capacity)

    def add(self, item):
        self._items.append(item)

    def snapshot(self):
        return tuple(self._items)

    def __len__(self):
        return len(self._items)
