"""World advanced 0104.
"""
from __future__ import annotations

WORLD = "world_adv_0104"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (104 % 8), "biome": ["ash", "crystal", "void", "rift"][104 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
