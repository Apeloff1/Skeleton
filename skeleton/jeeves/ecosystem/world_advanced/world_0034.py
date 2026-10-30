"""World advanced 0034.
"""
from __future__ import annotations

WORLD = "world_adv_0034"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (34 % 8), "biome": ["ash", "crystal", "void", "rift"][34 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
