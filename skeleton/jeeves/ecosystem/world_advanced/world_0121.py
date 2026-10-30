"""World advanced 0121.
"""
from __future__ import annotations

WORLD = "world_adv_0121"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (121 % 8), "biome": ["ash", "crystal", "void", "rift"][121 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
