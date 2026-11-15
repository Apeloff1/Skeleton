"""Synchronized bounded process-local retry credits."""
from threading import Lock


class RetryBudget:
    def __init__(self, attempts):
        if type(attempts) is not int or not 0 <= attempts <= (1 << 63) - 1:
            raise ValueError("attempts must be a bounded non-negative integer")
        self._capacity = attempts
        self._remaining = attempts
        self._lock = Lock()

    @property
    def capacity(self):
        return self._capacity

    @property
    def remaining(self):
        with self._lock:
            return self._remaining

    @property
    def exhausted(self):
        return self.remaining == 0

    @property
    def consumed(self):
        return self._capacity - self.remaining

    def consume(self):
        with self._lock:
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            return True

    def reset(self):
        with self._lock:
            self._remaining = self._capacity
            return self._remaining
