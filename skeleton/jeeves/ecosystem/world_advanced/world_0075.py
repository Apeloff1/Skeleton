"""World advanced 0075.
"""
from __future__ import annotations

WORLD = "world_adv_0075"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (75 % 8), "biome": ["ash", "crystal", "void", "rift"][75 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
