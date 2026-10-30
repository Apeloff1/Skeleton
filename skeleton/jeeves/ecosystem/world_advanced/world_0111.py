"""World advanced 0111.
"""
from __future__ import annotations

WORLD = "world_adv_0111"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (111 % 8), "biome": ["ash", "crystal", "void", "rift"][111 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
