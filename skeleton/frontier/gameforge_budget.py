"""Hierarchical budget: child reservations cannot exceed parent capacity."""
from threading import Lock


class Budget:
    def __init__(self, capacity: int):
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self.used = 0
        self._lock = Lock()

    @property
    def remaining(self):
        with self._lock:
            return self.capacity - self.used

    @property
    def exhausted(self):
        with self._lock:
            return self.used >= self.capacity

    def reserve(self, amount: int = 1) -> bool:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("amount must be a positive integer")
        with self._lock:
            if self.used + amount > self.capacity:
                return False
            self.used += amount
            return True

    def release(self, amount: int = 1):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("invalid release")
        with self._lock:
            if amount > self.used:
                raise ValueError("invalid release")
            self.used -= amount
