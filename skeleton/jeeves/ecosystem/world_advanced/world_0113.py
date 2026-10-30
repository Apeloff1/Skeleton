"""World advanced 0113.
"""
from __future__ import annotations

WORLD = "world_adv_0113"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (113 % 8), "biome": ["ash", "crystal", "void", "rift"][113 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
