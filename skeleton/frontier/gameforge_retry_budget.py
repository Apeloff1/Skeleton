"""Bounded retry budget preventing unbounded recovery amplification."""
from threading import Lock


class RetryBudget:
    def __init__(self, attempts):
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
            raise ValueError("attempts must be a non-negative integer")
        self.capacity = attempts
        self.remaining = attempts
        self._lock = Lock()

    @property
    def exhausted(self):
        with self._lock:
            return self.remaining == 0

    @property
    def consumed(self):
        with self._lock:
            return self.capacity - self.remaining

    def consume(self):
        with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True

    def reset(self):
        with self._lock:
            self.remaining = self.capacity
            return self.remaining
