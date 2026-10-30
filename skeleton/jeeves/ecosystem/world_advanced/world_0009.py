"""World advanced 0009.
"""
from __future__ import annotations

WORLD = "world_adv_0009"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (9 % 8), "biome": ["ash", "crystal", "void", "rift"][9 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
