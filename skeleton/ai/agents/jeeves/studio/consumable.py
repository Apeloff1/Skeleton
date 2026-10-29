"""Consumable. Single-use items with effects."""
from typing import Any, Dict
class Consumable:
    def __init__(self, name: str, effect: str, magnitude: float):
        self.name = name
        self.effect = effect
        self.magnitude = magnitude
        self.used = False
    def use(self) -> Dict[str, Any]:
        if self.used: return {"ok": False}
        self.used = True
        return {"ok": True, "effect": self.effect, "magnitude": self.magnitude}
