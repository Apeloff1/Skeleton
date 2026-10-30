"""World advanced 0058.
"""
from __future__ import annotations

WORLD = "world_adv_0058"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (58 % 8), "biome": ["ash", "crystal", "void", "rift"][58 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
