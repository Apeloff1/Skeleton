"""World advanced 0074.
"""
from __future__ import annotations

WORLD = "world_adv_0074"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (74 % 8), "biome": ["ash", "crystal", "void", "rift"][74 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
