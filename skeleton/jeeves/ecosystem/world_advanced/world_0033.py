"""World advanced 0033.
"""
from __future__ import annotations

WORLD = "world_adv_0033"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (33 % 8), "biome": ["ash", "crystal", "void", "rift"][33 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
