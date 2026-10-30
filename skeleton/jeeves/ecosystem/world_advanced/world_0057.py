"""World advanced 0057.
"""
from __future__ import annotations

WORLD = "world_adv_0057"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (57 % 8), "biome": ["ash", "crystal", "void", "rift"][57 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
