"""World advanced 0096.
"""
from __future__ import annotations

WORLD = "world_adv_0096"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (96 % 8), "biome": ["ash", "crystal", "void", "rift"][96 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
