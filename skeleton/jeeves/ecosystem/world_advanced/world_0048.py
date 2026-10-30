"""World advanced 0048.
"""
from __future__ import annotations

WORLD = "world_adv_0048"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (48 % 8), "biome": ["ash", "crystal", "void", "rift"][48 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
