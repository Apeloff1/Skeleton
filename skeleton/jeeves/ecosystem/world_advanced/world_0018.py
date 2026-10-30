"""World advanced 0018.
"""
from __future__ import annotations

WORLD = "world_adv_0018"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (18 % 8), "biome": ["ash", "crystal", "void", "rift"][18 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
