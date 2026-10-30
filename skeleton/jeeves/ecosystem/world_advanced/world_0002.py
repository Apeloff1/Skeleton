"""World advanced 0002.
"""
from __future__ import annotations

WORLD = "world_adv_0002"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (2 % 8), "biome": ["ash", "crystal", "void", "rift"][2 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
