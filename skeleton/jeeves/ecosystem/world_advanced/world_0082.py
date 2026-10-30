"""World advanced 0082.
"""
from __future__ import annotations

WORLD = "world_adv_0082"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (82 % 8), "biome": ["ash", "crystal", "void", "rift"][82 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
