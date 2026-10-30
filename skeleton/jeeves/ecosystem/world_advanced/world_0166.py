"""World advanced 0166.
"""
from __future__ import annotations

WORLD = "world_adv_0166"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (166 % 8), "biome": ["ash", "crystal", "void", "rift"][166 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
