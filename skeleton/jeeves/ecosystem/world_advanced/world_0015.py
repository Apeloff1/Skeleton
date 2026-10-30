"""World advanced 0015.
"""
from __future__ import annotations

WORLD = "world_adv_0015"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (15 % 8), "biome": ["ash", "crystal", "void", "rift"][15 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
