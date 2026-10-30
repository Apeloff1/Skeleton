"""World advanced 0144.
"""
from __future__ import annotations

WORLD = "world_adv_0144"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (144 % 8), "biome": ["ash", "crystal", "void", "rift"][144 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
