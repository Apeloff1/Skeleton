"""World advanced 0049.
"""
from __future__ import annotations

WORLD = "world_adv_0049"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (49 % 8), "biome": ["ash", "crystal", "void", "rift"][49 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
