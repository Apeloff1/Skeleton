"""Large world data subsystem.
Biome templates, room archetypes, connection rules, difficulty curves.
"""
from __future__ import annotations
from typing import Any, Dict, List

BIOME_TEMPLATES = {
    "ash_tunnel": {"base_diff": 0.35, "hazard": 0.12, "pack_density": 0.32, "enemy_types": ["patrol", "chaser"]},
    "crystal_cavern": {"base_diff": 0.42, "hazard": 0.18, "pack_density": 0.28, "enemy_types": ["chaser", "turret"]},
    "rust_foundry": {"base_diff": 0.48, "hazard": 0.22, "pack_density": 0.35, "enemy_types": ["patrol", "turret"]},
    "void_rift": {"base_diff": 0.65, "hazard": 0.30, "pack_density": 0.20, "enemy_types": ["chaser"]},
    "ember_hall": {"base_diff": 0.55, "hazard": 0.25, "pack_density": 0.30, "enemy_types": ["patrol", "chaser"]},
    "ice_vault": {"base_diff": 0.40, "hazard": 0.15, "pack_density": 0.33, "enemy_types": ["turret"]},
    "spore_garden": {"base_diff": 0.38, "hazard": 0.20, "pack_density": 0.40, "enemy_types": ["patrol"]},
    "clockwork_hall": {"base_diff": 0.50, "hazard": 0.16, "pack_density": 0.27, "enemy_types": ["chaser", "turret"]},
}

ROOM_ARCHETYPES = [
    {"id": 0, "size": "small", "exits": 2, "loot_bias": 0.25},
    {"id": 1, "size": "medium", "exits": 3, "loot_bias": 0.30},
    {"id": 2, "size": "large", "exits": 4, "loot_bias": 0.35},
    {"id": 3, "size": "small", "exits": 2, "loot_bias": 0.28},
    {"id": 4, "size": "medium", "exits": 3, "loot_bias": 0.32},
]

class WorldData:
    def get_biome(self, name: str) -> Dict[str, Any]:
        return BIOME_TEMPLATES.get(name, BIOME_TEMPLATES["ash_tunnel"])
    def sample_rooms(self, count: int = 12) -> List[Dict[str, Any]]:
        return [ROOM_ARCHETYPES[i % len(ROOM_ARCHETYPES)] for i in range(count)]
