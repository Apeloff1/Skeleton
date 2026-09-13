"""Deterministic deadline budget accounting."""


class Deadline:
    def __init__(self, budget: int):
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
            raise ValueError("budget must be a non-negative integer")
        self.capacity = budget
        self.remaining = budget

    @property
    def exhausted(self):
        return self.remaining == 0

    def spend(self, cost: int) -> bool:
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
            raise ValueError("cost must be a non-negative integer")
        if cost > self.remaining:
            self.remaining = 0
            return False
        self.remaining -= cost
        return True

    def reset(self):
        self.remaining = self.capacity
