"""World advanced 0061.
"""
from __future__ import annotations

WORLD = "world_adv_0061"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (61 % 8), "biome": ["ash", "crystal", "void", "rift"][61 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
