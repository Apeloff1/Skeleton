"""World advanced 0067.
"""
from __future__ import annotations

WORLD = "world_adv_0067"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (67 % 8), "biome": ["ash", "crystal", "void", "rift"][67 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
