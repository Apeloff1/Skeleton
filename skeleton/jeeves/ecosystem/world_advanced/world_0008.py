"""World advanced 0008.
"""
from __future__ import annotations

WORLD = "world_adv_0008"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (8 % 8), "biome": ["ash", "crystal", "void", "rift"][8 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
