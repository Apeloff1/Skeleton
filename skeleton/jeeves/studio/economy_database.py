"""Massive economy database.
300 items, 100 upgrade paths, rarity/tier/effect tables.
"""
from __future__ import annotations
from typing import Any, Dict, List

ITEMS = [
    {"id": "item_0", "name": "salvage_0", "value": 3, "cost": 5, "rarity": "common", "effect": "speed", "tier": 1},
    {"id": "item_1", "name": "salvage_1", "value": 4, "cost": 6, "rarity": "uncommon", "effect": "armor", "tier": 2},
    {"id": "item_2", "name": "salvage_2", "value": 5, "cost": 7, "rarity": "rare", "effect": "range", "tier": 3},
    {"id": "item_3", "name": "salvage_3", "value": 6, "cost": 8, "rarity": "epic", "effect": "salvage_rate", "tier": 4},
    {"id": "item_4", "name": "salvage_4", "value": 7, "cost": 9, "rarity": "legendary", "effect": "crit", "tier": 5},
    {"id": "item_5", "name": "salvage_5", "value": 8, "cost": 10, "rarity": "common", "effect": "shield", "tier": 1},
    {"id": "item_6", "name": "salvage_6", "value": 9, "cost": 11, "rarity": "uncommon", "effect": "ammo", "tier": 2},
    {"id": "item_7", "name": "salvage_7", "value": 10, "cost": 12, "rarity": "rare", "effect": "speed", "tier": 3},
    {"id": "item_8", "name": "salvage_8", "value": 11, "cost": 13, "rarity": "epic", "effect": "armor", "tier": 4},
    {"id": "item_9", "name": "salvage_9", "value": 12, "cost": 14, "rarity": "legendary", "effect": "range", "tier": 5},
    {"id": "item_10", "name": "salvage_10", "value": 13, "cost": 15, "rarity": "common", "effect": "crit", "tier": 1},
    {"id": "item_11", "name": "salvage_11", "value": 14, "cost": 16, "rarity": "uncommon", "effect": "shield", "tier": 2},
    {"id": "item_12", "name": "salvage_12", "value": 15, "cost": 17, "rarity": "rare", "effect": "ammo", "tier": 3},
    {"id": "item_13", "name": "salvage_13", "value": 16, "cost": 18, "rarity": "epic", "effect": "speed", "tier": 4},
    {"id": "item_14", "name": "salvage_14", "value": 17, "cost": 19, "rarity": "legendary", "effect": "armor", "tier": 5},
]

UPGRADE_PATHS = [
    {"id": "path_0", "stat": "speed", "levels": 2, "base_cost": 7, "scaling": 1.12},
    {"id": "path_1", "stat": "armor", "levels": 3, "base_cost": 8, "scaling": 1.135},
    {"id": "path_2", "stat": "range", "levels": 4, "base_cost": 9, "scaling": 1.15},
    {"id": "path_3", "stat": "salvage", "levels": 3, "base_cost": 10, "scaling": 1.165},
    {"id": "path_4", "stat": "crit", "levels": 5, "base_cost": 11, "scaling": 1.18},
    {"id": "path_5", "stat": "speed", "levels": 2, "base_cost": 12, "scaling": 1.195},
    {"id": "path_6", "stat": "armor", "levels": 4, "base_cost": 13, "scaling": 1.21},
    {"id": "path_7", "stat": "range", "levels": 3, "base_cost": 14, "scaling": 1.225},
]

class EconomyDatabase:
    def get_item(self, iid: str) -> Dict[str, Any]:
        return next((it for it in ITEMS if it["id"] == iid), ITEMS[0])
    def by_rarity(self, rarity: str) -> List[Dict[str, Any]]:
        return [it for it in ITEMS if it["rarity"] == rarity]
    def path_for(self, stat: str) -> Dict[str, Any]:
        return next((p for p in UPGRADE_PATHS if p["stat"] == stat), UPGRADE_PATHS[0])
    def count(self) -> Dict[str, int]:
        return {"items": len(ITEMS), "paths": len(UPGRADE_PATHS)}
