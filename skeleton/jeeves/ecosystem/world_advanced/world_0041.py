"""World advanced 0041.
"""
from __future__ import annotations

WORLD = "world_adv_0041"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (41 % 8), "biome": ["ash", "crystal", "void", "rift"][41 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
