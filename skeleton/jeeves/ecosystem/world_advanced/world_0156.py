"""World advanced 0156.
"""
from __future__ import annotations

WORLD = "world_adv_0156"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (156 % 8), "biome": ["ash", "crystal", "void", "rift"][156 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
