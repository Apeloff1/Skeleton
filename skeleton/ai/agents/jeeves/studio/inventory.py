"""Inventory system.
Tracks salvage, equipped upgrades, capacity, and spend validation.
"""
from __future__ import annotations
from typing import Any, Dict, List

class Inventory:
    def __init__(self, capacity: int = 20):
        self.capacity = capacity
        self.items: List[Dict[str, Any]] = []
        self.equipped: Dict[str, str] = {}
    def add(self, item: Dict[str, Any]) -> bool:
        if len(self.items) >= self.capacity:
            return False
        self.items.append(item)
        return True
    def equip(self, item_id: str, slot: str) -> bool:
        found = next((it for it in self.items if it.get("id") == item_id), None)
        if not found:
            return False
        self.equipped[slot] = item_id
        return True
    def modifiers(self) -> Dict[str, float]:
        speed = 1.0
        armor = 0.0
        for iid in self.equipped.values():
            it = next((x for x in self.items if x.get("id") == iid), {})
            if it.get("effect") == "speed":
                speed += 0.1
            if it.get("effect") == "armor":
                armor += 5.0
        return {"speed": speed, "armor": armor}
    def status(self) -> Dict[str, Any]:
        return {"count": len(self.items), "capacity": self.capacity, "equipped": self.equipped}
