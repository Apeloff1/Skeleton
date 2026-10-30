"""World advanced 0101.
"""
from __future__ import annotations

WORLD = "world_adv_0101"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (101 % 8), "biome": ["ash", "crystal", "void", "rift"][101 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
