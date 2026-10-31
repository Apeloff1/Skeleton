"""Skill tree.
Unlocks permanent modifiers from salvage spend and reputation.
"""
from __future__ import annotations
from typing import Any, Dict, List

NODES = [
    {"id": "swift", "cost": 20, "effect": "speed", "magnitude": 0.1, "requires": []},
    {"id": "tough", "cost": 25, "effect": "armor", "magnitude": 8, "requires": []},
    {"id": "keen", "cost": 30, "effect": "crit", "magnitude": 0.08, "requires": ["swift"]},
    {"id": "optical_attune", "cost": 35, "effect": "optical_gain", "magnitude": 0.03, "requires": ["keen"]},
]

class SkillTree:
    def __init__(self):
        self.unlocked: List[str] = []
    def can_unlock(self, node_id: str, salvage: int) -> bool:
        node = next((n for n in NODES if n["id"] == node_id), None)
        if not node or node_id in self.unlocked:
            return False
        if salvage < node["cost"]:
            return False
        return all(r in self.unlocked for r in node["requires"])
    def unlock(self, node_id: str, salvage: int) -> bool:
        if not self.can_unlock(node_id, salvage):
            return False
        self.unlocked.append(node_id)
        return True
    def modifiers(self) -> Dict[str, float]:
        mods = {"speed": 1.0, "armor": 0.0, "crit": 0.0, "optical_gain": 0.0}
        for nid in self.unlocked:
            node = next(n for n in NODES if n["id"] == nid)
            if node["effect"] == "speed":
                mods["speed"] += node["magnitude"]
            elif node["effect"] == "armor":
                mods["armor"] += node["magnitude"]
            elif node["effect"] == "crit":
                mods["crit"] += node["magnitude"]
            elif node["effect"] == "optical_gain":
                mods["optical_gain"] += node["magnitude"]
        return mods
