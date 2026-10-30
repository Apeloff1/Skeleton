"""World advanced 0107.
"""
from __future__ import annotations

WORLD = "world_adv_0107"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (107 % 8), "biome": ["ash", "crystal", "void", "rift"][107 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
