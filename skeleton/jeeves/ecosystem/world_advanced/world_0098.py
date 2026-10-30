"""World advanced 0098.
"""
from __future__ import annotations

WORLD = "world_adv_0098"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (98 % 8), "biome": ["ash", "crystal", "void", "rift"][98 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
