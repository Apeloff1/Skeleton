"""Combo system. Chains hits for bonus damage."""
from typing import Any, Dict
class ComboSystem:
    def __init__(self):
        self.hits = 0
        self.timer = 0.0
    def hit(self) -> int:
        self.hits += 1
        self.timer = 2.0
        return self.hits
    def tick(self, dt: float) -> None:
        self.timer -= dt
        if self.timer <= 0: self.hits = 0
    def multiplier(self) -> float:
        return 1.0 + min(self.hits, 10) * 0.05
