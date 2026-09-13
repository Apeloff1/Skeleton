"""Hierarchical budget: child reservations cannot exceed parent capacity."""


class Budget:
    def __init__(self, capacity: int):
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self.used = 0

    @property
    def remaining(self):
        return self.capacity - self.used

    @property
    def exhausted(self):
        return self.used >= self.capacity

    def reserve(self, amount: int = 1) -> bool:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("amount must be a positive integer")
        if self.used + amount > self.capacity:
            return False
        self.used += amount
        return True

    def release(self, amount: int = 1):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0 or amount > self.used:
            raise ValueError("invalid release")
        self.used -= amount
