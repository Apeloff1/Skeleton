"""World advanced 0013.
"""
from __future__ import annotations

WORLD = "world_adv_0013"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (13 % 8), "biome": ["ash", "crystal", "void", "rift"][13 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
