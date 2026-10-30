"""World advanced 0051.
"""
from __future__ import annotations

WORLD = "world_adv_0051"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (51 % 8), "biome": ["ash", "crystal", "void", "rift"][51 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
