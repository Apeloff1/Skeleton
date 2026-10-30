"""World advanced 0079.
"""
from __future__ import annotations

WORLD = "world_adv_0079"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (79 % 8), "biome": ["ash", "crystal", "void", "rift"][79 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
