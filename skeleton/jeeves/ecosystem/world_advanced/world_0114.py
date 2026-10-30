"""World advanced 0114.
"""
from __future__ import annotations

WORLD = "world_adv_0114"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (114 % 8), "biome": ["ash", "crystal", "void", "rift"][114 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
