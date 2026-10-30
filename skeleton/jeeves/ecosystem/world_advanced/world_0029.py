"""World advanced 0029.
"""
from __future__ import annotations

WORLD = "world_adv_0029"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (29 % 8), "biome": ["ash", "crystal", "void", "rift"][29 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
