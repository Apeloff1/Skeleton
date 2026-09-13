"""Bounded FIFO queue with explicit backpressure."""
from collections import deque
from threading import Lock


class BoundedQueue:
    def __init__(self, capacity):
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self._items = deque()
        self._lock = Lock()

    @property
    def remaining(self):
        with self._lock:
            return self.capacity - len(self._items)

    @property
    def full(self):
        with self._lock:
            return len(self._items) >= self.capacity

    def push(self, item):
        with self._lock:
            if len(self._items) >= self.capacity:
                return False
            self._items.append(item)
            return True

    def pop(self):
        with self._lock:
            return self._items.popleft() if self._items else None

    def remove(self, item):
        """Remove the first matching item without disturbing other reservations."""
        with self._lock:
            try:
                self._items.remove(item)
            except ValueError:
                return False
            return True

    def peek(self):
        with self._lock:
            return self._items[0] if self._items else None

    def clear(self):
        """Empty the queue and return the number of discarded items."""
        with self._lock:
            count = len(self._items)
            self._items.clear()
            return count

    def snapshot(self):
        """Return an immutable point-in-time view of queued items."""
        with self._lock:
            return tuple(self._items)

    def __len__(self):
        with self._lock:
            return len(self._items)
