"""World advanced 0089.
"""
from __future__ import annotations

WORLD = "world_adv_0089"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (89 % 8), "biome": ["ash", "crystal", "void", "rift"][89 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
