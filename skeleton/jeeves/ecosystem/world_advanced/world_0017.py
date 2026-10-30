"""World advanced 0017.
"""
from __future__ import annotations

WORLD = "world_adv_0017"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (17 % 8), "biome": ["ash", "crystal", "void", "rift"][17 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
