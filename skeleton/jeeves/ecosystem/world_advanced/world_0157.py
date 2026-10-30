"""World advanced 0157.
"""
from __future__ import annotations

WORLD = "world_adv_0157"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (157 % 8), "biome": ["ash", "crystal", "void", "rift"][157 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
