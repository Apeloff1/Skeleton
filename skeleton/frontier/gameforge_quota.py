"""Hierarchical quota composition for bounded runtime admission."""
from threading import Lock


class Quota:
    def __init__(self, limit):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        self.limit = limit
        self.used = 0
        self._lock = Lock()

    @property
    def remaining(self):
        with self._lock:
            return self.limit - self.used

    @property
    def exhausted(self):
        with self._lock:
            return self.used >= self.limit

    def reserve(self, amount=1):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("amount must be a positive integer")
        with self._lock:
            if self.used + amount > self.limit:
                return False
            self.used += amount
            return True

    def release(self, amount=1):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("invalid release")
        with self._lock:
            if amount > self.used:
                raise ValueError("invalid release")
            self.used -= amount
