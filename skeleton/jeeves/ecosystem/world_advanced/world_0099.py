"""World advanced 0099.
"""
from __future__ import annotations

WORLD = "world_adv_0099"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (99 % 8), "biome": ["ash", "crystal", "void", "rift"][99 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
