"""World advanced 0016.
"""
from __future__ import annotations

WORLD = "world_adv_0016"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (16 % 8), "biome": ["ash", "crystal", "void", "rift"][16 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
