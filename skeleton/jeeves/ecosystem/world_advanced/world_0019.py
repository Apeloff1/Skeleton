"""World advanced 0019.
"""
from __future__ import annotations

WORLD = "world_adv_0019"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (19 % 8), "biome": ["ash", "crystal", "void", "rift"][19 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
