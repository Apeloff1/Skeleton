"""Explicit budget policy for bounded admission."""
from dataclasses import dataclass

@dataclass(frozen=True)
class BudgetPolicy:
    capacity: int
    reserve_size: int = 1

    def __post_init__(self):
        if self.capacity <= 0 or self.reserve_size <= 0:
            raise ValueError("budget values must be positive")
        if self.reserve_size > self.capacity:
            raise ValueError("reserve_size exceeds capacity")

    def permits(self, used: int) -> bool:
        return used + self.reserve_size <= self.capacity
