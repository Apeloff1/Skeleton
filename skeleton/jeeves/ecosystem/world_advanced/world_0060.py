"""World advanced 0060.
"""
from __future__ import annotations

WORLD = "world_adv_0060"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (60 % 8), "biome": ["ash", "crystal", "void", "rift"][60 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
