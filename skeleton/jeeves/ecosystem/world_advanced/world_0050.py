"""World advanced 0050.
"""
from __future__ import annotations

WORLD = "world_adv_0050"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (50 % 8), "biome": ["ash", "crystal", "void", "rift"][50 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
