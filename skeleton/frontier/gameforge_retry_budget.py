"""Bounded retry budget preventing unbounded recovery amplification."""


class RetryBudget:
    def __init__(self, attempts):
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
            raise ValueError("attempts must be a non-negative integer")
        self.capacity = attempts
        self.remaining = attempts

    @property
    def exhausted(self):
        return self.remaining == 0

    @property
    def consumed(self):
        return self.capacity - self.remaining

    def consume(self):
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True

    def reset(self):
        self.remaining = self.capacity
        return self.remaining
