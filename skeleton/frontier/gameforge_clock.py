"""Deterministic logical clock for bounded frontier policies."""
class LogicalClock:
    def __init__(self, start: int = 0):
        self.value = start
    def tick(self, amount: int = 1) -> int:
        if amount <= 0: raise ValueError("amount must be positive")
        self.value += amount
        return self.value
