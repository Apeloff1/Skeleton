"""Economy and catalog subsystem.
Full item tables, upgrade trees, salvage rates, spend validation, mass clips.
"""
from __future__ import annotations
from typing import Any, Dict, List
import json

ITEMS = [
    {"id": "item_0", "name": "salvage_0", "value": 5, "cost": 8, "rarity": "common", "effect": "upgrade_0"},
    {"id": "item_1", "name": "salvage_1", "value": 6, "cost": 9, "rarity": "uncommon", "effect": "upgrade_1"},
    {"id": "item_2", "name": "salvage_2", "value": 7, "cost": 10, "rarity": "rare", "effect": "upgrade_2"},
    {"id": "item_3", "name": "salvage_3", "value": 8, "cost": 11, "rarity": "epic", "effect": "upgrade_3"},
    {"id": "item_4", "name": "salvage_4", "value": 9, "cost": 12, "rarity": "common", "effect": "upgrade_4"}
]

UPGRADES = [
    {"id": "upg_0", "stat": "speed", "delta": 0.05, "cost": 10, "prereq": 0},
    {"id": "upg_1", "stat": "armor", "delta": 0.06, "cost": 11, "prereq": 0}
]

class EconomySimulator:
    def __init__(self):
        self.salvage = 0
        self.applied = []
    def add(self, amount: int) -> int:
        self.salvage += amount
        return self.salvage
    def spend(self, cost: int, upgrade_id: str) -> bool:
        if self.salvage < cost:
            return False
        self.salvage -= cost
        self.applied.append(upgrade_id)
        return True
    def validate(self) -> Dict[str, Any]:
        return {"salvage": self.salvage, "applied_count": len(self.applied), "valid": self.salvage >= 0}
