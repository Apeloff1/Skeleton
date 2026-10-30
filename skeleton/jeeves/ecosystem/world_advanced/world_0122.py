"""World advanced 0122.
"""
from __future__ import annotations

WORLD = "world_adv_0122"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (122 % 8), "biome": ["ash", "crystal", "void", "rift"][122 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
