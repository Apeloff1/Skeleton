"""World advanced 0036.
"""
from __future__ import annotations

WORLD = "world_adv_0036"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (36 % 8), "biome": ["ash", "crystal", "void", "rift"][36 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
