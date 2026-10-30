"""World advanced 0150.
"""
from __future__ import annotations

WORLD = "world_adv_0150"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (150 % 8), "biome": ["ash", "crystal", "void", "rift"][150 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
