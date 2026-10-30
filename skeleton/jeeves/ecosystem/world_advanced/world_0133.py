"""World advanced 0133.
"""
from __future__ import annotations

WORLD = "world_adv_0133"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (133 % 8), "biome": ["ash", "crystal", "void", "rift"][133 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
