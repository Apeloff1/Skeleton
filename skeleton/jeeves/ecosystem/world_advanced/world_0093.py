"""World advanced 0093.
"""
from __future__ import annotations

WORLD = "world_adv_0093"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (93 % 8), "biome": ["ash", "crystal", "void", "rift"][93 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
