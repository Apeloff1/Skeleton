"""World advanced 0006.
"""
from __future__ import annotations

WORLD = "world_adv_0006"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (6 % 8), "biome": ["ash", "crystal", "void", "rift"][6 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
