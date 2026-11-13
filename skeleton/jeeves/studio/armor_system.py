"""Armor system. Damage reduction from equipped pieces."""
from typing import Any, Dict
class ArmorSystem:
    def __init__(self):
        self.pieces: Dict[str, float] = {}
    def equip(self, slot: str, reduction: float) -> None:
        self.pieces[slot] = reduction
    def total(self) -> float:
        return sum(self.pieces.values())
