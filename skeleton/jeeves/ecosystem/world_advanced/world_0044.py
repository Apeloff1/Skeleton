"""World advanced 0044.
"""
from __future__ import annotations

WORLD = "world_adv_0044"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (44 % 8), "biome": ["ash", "crystal", "void", "rift"][44 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
