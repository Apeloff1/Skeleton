"""World advanced 0080.
"""
from __future__ import annotations

WORLD = "world_adv_0080"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (80 % 8), "biome": ["ash", "crystal", "void", "rift"][80 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
