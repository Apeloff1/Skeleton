"""World advanced 0137.
"""
from __future__ import annotations

WORLD = "world_adv_0137"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (137 % 8), "biome": ["ash", "crystal", "void", "rift"][137 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
