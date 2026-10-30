"""World advanced 0176.
"""
from __future__ import annotations

WORLD = "world_adv_0176"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (176 % 8), "biome": ["ash", "crystal", "void", "rift"][176 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
