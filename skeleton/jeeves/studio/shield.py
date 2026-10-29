"""Shield. Temporary damage absorption."""
from typing import Any, Dict
class Shield:
    def __init__(self, amount: float = 0.0):
        self.amount = amount
    def absorb(self, damage: float) -> float:
        blocked = min(self.amount, damage)
        self.amount -= blocked
        return damage - blocked
