"""World advanced 0164.
"""
from __future__ import annotations

WORLD = "world_adv_0164"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (164 % 8), "biome": ["ash", "crystal", "void", "rift"][164 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
