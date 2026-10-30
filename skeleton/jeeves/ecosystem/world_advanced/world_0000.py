"""World advanced 0000.
"""
from __future__ import annotations

WORLD = "world_adv_0000"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (0 % 8), "biome": ["ash", "crystal", "void", "rift"][0 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
