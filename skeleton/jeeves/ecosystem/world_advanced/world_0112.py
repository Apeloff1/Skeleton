"""World advanced 0112.
"""
from __future__ import annotations

WORLD = "world_adv_0112"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (112 % 8), "biome": ["ash", "crystal", "void", "rift"][112 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
