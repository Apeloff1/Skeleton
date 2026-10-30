"""World advanced 0024.
"""
from __future__ import annotations

WORLD = "world_adv_0024"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (24 % 8), "biome": ["ash", "crystal", "void", "rift"][24 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
