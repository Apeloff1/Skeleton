"""World advanced 0070.
"""
from __future__ import annotations

WORLD = "world_adv_0070"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (70 % 8), "biome": ["ash", "crystal", "void", "rift"][70 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
