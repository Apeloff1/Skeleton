"""World advanced 0081.
"""
from __future__ import annotations

WORLD = "world_adv_0081"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (81 % 8), "biome": ["ash", "crystal", "void", "rift"][81 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
