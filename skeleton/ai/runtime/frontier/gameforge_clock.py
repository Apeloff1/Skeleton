"""Deterministic logical clock for bounded frontier policies."""


class LogicalClock:
    def __init__(self, start: int = 0):
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            raise ValueError("start must be a non-negative integer")
        self.value = start

    def tick(self, amount: int = 1) -> int:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("amount must be a positive integer")
        self.value += amount
        return self.value
