"""Collectible. Optional lore or optical fragments."""
from typing import Any, Dict
class Collectible:
    def __init__(self, id: str, optical_bonus: float = 0.01):
        self.id = id
        self.bonus = optical_bonus
        self.collected = False
    def collect(self) -> float:
        if self.collected: return 0.0
        self.collected = True
        return self.bonus
