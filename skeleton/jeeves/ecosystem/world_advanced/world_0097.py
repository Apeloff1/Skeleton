"""World advanced 0097.
"""
from __future__ import annotations

WORLD = "world_adv_0097"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (97 % 8), "biome": ["ash", "crystal", "void", "rift"][97 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
