"""World advanced 0004.
"""
from __future__ import annotations

WORLD = "world_adv_0004"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (4 % 8), "biome": ["ash", "crystal", "void", "rift"][4 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
