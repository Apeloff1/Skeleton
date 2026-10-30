"""World advanced 0152.
"""
from __future__ import annotations

WORLD = "world_adv_0152"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (152 % 8), "biome": ["ash", "crystal", "void", "rift"][152 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
