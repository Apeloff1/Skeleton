"""World advanced 0001.
"""
from __future__ import annotations

WORLD = "world_adv_0001"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (1 % 8), "biome": ["ash", "crystal", "void", "rift"][1 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
