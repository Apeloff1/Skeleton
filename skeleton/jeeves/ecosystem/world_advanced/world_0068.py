"""World advanced 0068.
"""
from __future__ import annotations

WORLD = "world_adv_0068"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (68 % 8), "biome": ["ash", "crystal", "void", "rift"][68 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
