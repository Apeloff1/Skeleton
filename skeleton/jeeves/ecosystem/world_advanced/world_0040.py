"""World advanced 0040.
"""
from __future__ import annotations

WORLD = "world_adv_0040"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (40 % 8), "biome": ["ash", "crystal", "void", "rift"][40 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
