"""World advanced 0126.
"""
from __future__ import annotations

WORLD = "world_adv_0126"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (126 % 8), "biome": ["ash", "crystal", "void", "rift"][126 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
