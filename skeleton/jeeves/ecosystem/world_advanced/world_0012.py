"""World advanced 0012.
"""
from __future__ import annotations

WORLD = "world_adv_0012"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (12 % 8), "biome": ["ash", "crystal", "void", "rift"][12 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
