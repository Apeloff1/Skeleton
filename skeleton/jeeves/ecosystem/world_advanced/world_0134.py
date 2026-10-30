"""World advanced 0134.
"""
from __future__ import annotations

WORLD = "world_adv_0134"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (134 % 8), "biome": ["ash", "crystal", "void", "rift"][134 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
