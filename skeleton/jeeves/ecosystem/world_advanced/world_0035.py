"""World advanced 0035.
"""
from __future__ import annotations

WORLD = "world_adv_0035"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (35 % 8), "biome": ["ash", "crystal", "void", "rift"][35 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
