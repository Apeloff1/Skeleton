"""Ammo system. Tracks and spends ammo for ranged attacks."""
from typing import Any, Dict
class AmmoSystem:
    def __init__(self, max_ammo: int = 30):
        self.max = max_ammo
        self.current = max_ammo
    def fire(self, cost: int = 1) -> bool:
        if self.current < cost: return False
        self.current -= cost
        return True
    def reload(self, amount: int) -> None:
        self.current = min(self.max, self.current + amount)
