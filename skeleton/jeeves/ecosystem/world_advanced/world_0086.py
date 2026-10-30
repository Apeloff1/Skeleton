"""World advanced 0086.
"""
from __future__ import annotations

WORLD = "world_adv_0086"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (86 % 8), "biome": ["ash", "crystal", "void", "rift"][86 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
