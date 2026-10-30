"""World advanced 0128.
"""
from __future__ import annotations

WORLD = "world_adv_0128"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (128 % 8), "biome": ["ash", "crystal", "void", "rift"][128 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
