"""World advanced 0021.
"""
from __future__ import annotations

WORLD = "world_adv_0021"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (21 % 8), "biome": ["ash", "crystal", "void", "rift"][21 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
