"""World advanced 0120.
"""
from __future__ import annotations

WORLD = "world_adv_0120"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (120 % 8), "biome": ["ash", "crystal", "void", "rift"][120 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
