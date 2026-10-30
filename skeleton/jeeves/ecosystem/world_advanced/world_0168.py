"""World advanced 0168.
"""
from __future__ import annotations

WORLD = "world_adv_0168"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (168 % 8), "biome": ["ash", "crystal", "void", "rift"][168 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
