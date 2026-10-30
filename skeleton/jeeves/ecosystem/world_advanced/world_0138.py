"""World advanced 0138.
"""
from __future__ import annotations

WORLD = "world_adv_0138"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (138 % 8), "biome": ["ash", "crystal", "void", "rift"][138 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
