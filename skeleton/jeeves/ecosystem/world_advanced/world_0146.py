"""World advanced 0146.
"""
from __future__ import annotations

WORLD = "world_adv_0146"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (146 % 8), "biome": ["ash", "crystal", "void", "rift"][146 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
