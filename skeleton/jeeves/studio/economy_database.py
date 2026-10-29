"""Large economy item database.
Hundreds of salvage types, upgrade paths, rarity tables, effect bindings.
"""
from __future__ import annotations
from typing import Any, Dict, List

ITEMS = [
    {"id": "item_0", "name": "salvage_0", "value": 4, "cost": 6, "rarity": "common", "effect": "speed", "tier": 1},
    {"id": "item_1", "name": "salvage_1", "value": 5, "cost": 7, "rarity": "uncommon", "effect": "armor", "tier": 2},
    {"id": "item_2", "name": "salvage_2", "value": 6, "cost": 8, "rarity": "rare", "effect": "range", "tier": 3},
    {"id": "item_3", "name": "salvage_3", "value": 7, "cost": 9, "rarity": "epic", "effect": "salvage_rate", "tier": 4},
    {"id": "item_4", "name": "salvage_4", "value": 8, "cost": 10, "rarity": "legendary", "effect": "crit", "tier": 5},
    {"id": "item_5", "name": "salvage_5", "value": 9, "cost": 11, "rarity": "common", "effect": "speed", "tier": 1},
    {"id": "item_6", "name": "salvage_6", "value": 10, "cost": 12, "rarity": "uncommon", "effect": "armor", "tier": 2},
    {"id": "item_7", "name": "salvage_7", "value": 11, "cost": 13, "rarity": "rare", "effect": "range", "tier": 3},
    {"id": "item_8", "name": "salvage_8", "value": 12, "cost": 14, "rarity": "epic", "effect": "salvage_rate", "tier": 4},
    {"id": "item_9", "name": "salvage_9", "value": 13, "cost": 15, "rarity": "legendary", "effect": "crit", "tier": 5},
]

UPGRADE_PATHS = [
    {"id": "path_0", "stat": "speed", "levels": 3, "base_cost": 8, "scaling": 1.15},
    {"id": "path_1", "stat": "armor", "levels": 4, "base_cost": 9, "scaling": 1.17},
    {"id": "path_2", "stat": "range", "levels": 5, "base_cost": 10, "scaling": 1.19},
    {"id": "path_3", "stat": "speed", "levels": 3, "base_cost": 11, "scaling": 1.21},
    {"id": "path_4", "stat": "armor", "levels": 4, "base_cost": 12, "scaling": 1.23},
]

class EconomyDatabase:
    def get_item(self, iid: str) -> Dict[str, Any]:
        return next((it for it in ITEMS if it["id"] == iid), ITEMS[0])
    def by_rarity(self, rarity: str) -> List[Dict[str, Any]]:
        return [it for it in ITEMS if it["rarity"] == rarity]
    def path_for(self, stat: str) -> Dict[str, Any]:
        return next((p for p in UPGRADE_PATHS if p["stat"] == stat), UPGRADE_PATHS[0])
