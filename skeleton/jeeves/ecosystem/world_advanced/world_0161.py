"""World advanced 0161.
"""
from __future__ import annotations

WORLD = "world_adv_0161"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (161 % 8), "biome": ["ash", "crystal", "void", "rift"][161 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
