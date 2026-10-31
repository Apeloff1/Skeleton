"""Weapon system. Equipped weapon stats and swap."""
from typing import Any, Dict, Optional
class WeaponSystem:
    def __init__(self):
        self.equipped: Optional[Dict[str, Any]] = None
    def equip(self, weapon: Dict[str, Any]) -> None:
        self.equipped = weapon
    def damage(self) -> float:
        return self.equipped.get("damage", 5.0) if self.equipped else 5.0
