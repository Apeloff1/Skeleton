"""World advanced 0010.
"""
from __future__ import annotations

WORLD = "world_adv_0010"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (10 % 8), "biome": ["ash", "crystal", "void", "rift"][10 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
