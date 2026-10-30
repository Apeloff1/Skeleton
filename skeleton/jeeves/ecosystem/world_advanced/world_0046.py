"""World advanced 0046.
"""
from __future__ import annotations

WORLD = "world_adv_0046"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (46 % 8), "biome": ["ash", "crystal", "void", "rift"][46 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
