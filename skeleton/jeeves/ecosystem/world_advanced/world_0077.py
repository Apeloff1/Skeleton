"""World advanced 0077.
"""
from __future__ import annotations

WORLD = "world_adv_0077"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (77 % 8), "biome": ["ash", "crystal", "void", "rift"][77 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
