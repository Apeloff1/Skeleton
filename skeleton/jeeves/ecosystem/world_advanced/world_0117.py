"""World advanced 0117.
"""
from __future__ import annotations

WORLD = "world_adv_0117"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (117 % 8), "biome": ["ash", "crystal", "void", "rift"][117 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
