"""World advanced 0094.
"""
from __future__ import annotations

WORLD = "world_adv_0094"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (94 % 8), "biome": ["ash", "crystal", "void", "rift"][94 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
