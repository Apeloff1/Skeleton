"""World advanced 0124.
"""
from __future__ import annotations

WORLD = "world_adv_0124"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (124 % 8), "biome": ["ash", "crystal", "void", "rift"][124 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
