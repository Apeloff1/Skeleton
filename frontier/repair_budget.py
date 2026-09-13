"""Bounded work budget for deterministic frontier passes."""


class WorkBudget:
    def __init__(self, capacity: int) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._spent = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def spent(self) -> int:
        return self._spent

    @property
    def remaining(self) -> int:
        return self._capacity - self._spent

    def consume(self, amount: int = 1) -> bool:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
            raise ValueError("amount must be a positive integer")
        if amount > self.remaining:
            return False
        self._spent += amount
        return True
