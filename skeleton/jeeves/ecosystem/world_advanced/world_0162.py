"""World advanced 0162.
"""
from __future__ import annotations

WORLD = "world_adv_0162"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (162 % 8), "biome": ["ash", "crystal", "void", "rift"][162 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
