"""World advanced 0159.
"""
from __future__ import annotations

WORLD = "world_adv_0159"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (159 % 8), "biome": ["ash", "crystal", "void", "rift"][159 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
