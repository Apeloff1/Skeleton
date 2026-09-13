"""Deterministic deadline budget accounting."""


class Deadline:
    def __init__(self, budget: int):
        if not isinstance(budget, int) or budget < 0:
            raise ValueError("budget must be non-negative")
        self.capacity = budget
        self.remaining = budget

    @property
    def exhausted(self):
        return self.remaining == 0

    def spend(self, cost: int) -> bool:
        if not isinstance(cost, int) or cost < 0:
            raise ValueError("cost must be non-negative")
        if cost > self.remaining:
            self.remaining = 0
            return False
        self.remaining -= cost
        return True

    def reset(self):
        self.remaining = self.capacity
