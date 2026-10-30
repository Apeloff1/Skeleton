"""World advanced 0054.
"""
from __future__ import annotations

WORLD = "world_adv_0054"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (54 % 8), "biome": ["ash", "crystal", "void", "rift"][54 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
