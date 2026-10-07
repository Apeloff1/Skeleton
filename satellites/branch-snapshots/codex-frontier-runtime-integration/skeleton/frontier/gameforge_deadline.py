"""Deterministic deadline budget accounting."""

from threading import Lock


class Deadline:
    def __init__(self, budget: int):
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
            raise ValueError("budget must be a non-negative integer")
        self.capacity = budget
        self.remaining = budget
        self._lock = Lock()

    @property
    def exhausted(self):
        with self._lock:
            return self.remaining == 0

    def spend(self, cost: int) -> bool:
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
            raise ValueError("cost must be a non-negative integer")
        with self._lock:
            if cost > self.remaining:
                self.remaining = 0
                return False
            self.remaining -= cost
            return True

    def reset(self):
        with self._lock:
            self.remaining = self.capacity
