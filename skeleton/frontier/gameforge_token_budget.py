"""Small deterministic token budget for bounded execution work."""
class TokenBudget:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.used = 0

    @property
    def remaining(self):
        return self.capacity - self.used

    def consume(self, amount: int = 1) -> bool:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if self.used + amount > self.capacity:
            return False
        self.used += amount
        return True

    def reset(self):
        self.used = 0
