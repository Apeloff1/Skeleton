"""Crafting system.
Combines salvage and items into upgrades or consumables.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

RECIPES = [
    {"id": "speed_tonic", "inputs": {"salvage": 15}, "output": {"effect": "speed", "magnitude": 0.15, "duration": 30}},
    {"id": "armor_plate", "inputs": {"salvage": 25, "item_rare": 1}, "output": {"effect": "armor", "magnitude": 12}},
    {"id": "range_lens", "inputs": {"salvage": 20}, "output": {"effect": "range", "magnitude": 0.1}},
    {"id": "optical_flare", "inputs": {"salvage": 10}, "output": {"effect": "optical_boost", "magnitude": 0.05, "duration": 20}},
]

class CraftingSystem:
    def craft(self, recipe_id: str, inventory: Dict[str, int]) -> Optional[Dict[str, Any]]:
        recipe = next((r for r in RECIPES if r["id"] == recipe_id), None)
        if not recipe:
            return None
        for k, need in recipe["inputs"].items():
            if inventory.get(k, 0) < need:
                return None
        return recipe["output"]
    def available(self, inventory: Dict[str, int]) -> List[str]:
        out = []
        for r in RECIPES:
            if all(inventory.get(k, 0) >= v for k, v in r["inputs"].items()):
                out.append(r["id"])
        return out
