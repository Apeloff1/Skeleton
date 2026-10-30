"""World advanced 0145.
"""
from __future__ import annotations

WORLD = "world_adv_0145"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (145 % 8), "biome": ["ash", "crystal", "void", "rift"][145 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
