"""World advanced 0109.
"""
from __future__ import annotations

WORLD = "world_adv_0109"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (109 % 8), "biome": ["ash", "crystal", "void", "rift"][109 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
