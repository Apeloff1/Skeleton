"""World advanced 0030.
"""
from __future__ import annotations

WORLD = "world_adv_0030"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (30 % 8), "biome": ["ash", "crystal", "void", "rift"][30 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
