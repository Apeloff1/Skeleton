"""World advanced 0023.
"""
from __future__ import annotations

WORLD = "world_adv_0023"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (23 % 8), "biome": ["ash", "crystal", "void", "rift"][23 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
