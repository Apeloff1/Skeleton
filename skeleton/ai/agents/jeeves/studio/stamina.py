"""Stamina. Sprint and dodge resource."""
from typing import Any, Dict
class Stamina:
    def __init__(self, max_s: float = 100.0):
        self.max = max_s
        self.current = max_s
    def use(self, amount: float) -> bool:
        if self.current < amount: return False
        self.current -= amount
        return True
    def regen(self, dt: float, rate: float = 20.0) -> None:
        self.current = min(self.max, self.current + rate * dt)
