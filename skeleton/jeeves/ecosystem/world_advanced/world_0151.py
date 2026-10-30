"""World advanced 0151.
"""
from __future__ import annotations

WORLD = "world_adv_0151"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (151 % 8), "biome": ["ash", "crystal", "void", "rift"][151 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
