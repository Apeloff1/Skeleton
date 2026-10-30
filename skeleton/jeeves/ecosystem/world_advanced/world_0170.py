"""World advanced 0170.
"""
from __future__ import annotations

WORLD = "world_adv_0170"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (170 % 8), "biome": ["ash", "crystal", "void", "rift"][170 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
