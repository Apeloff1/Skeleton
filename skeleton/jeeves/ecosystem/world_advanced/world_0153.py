"""World advanced 0153.
"""
from __future__ import annotations

WORLD = "world_adv_0153"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (153 % 8), "biome": ["ash", "crystal", "void", "rift"][153 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
