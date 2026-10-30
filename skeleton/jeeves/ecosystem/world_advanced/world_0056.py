"""World advanced 0056.
"""
from __future__ import annotations

WORLD = "world_adv_0056"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (56 % 8), "biome": ["ash", "crystal", "void", "rift"][56 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
