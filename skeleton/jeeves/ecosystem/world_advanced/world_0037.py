"""World advanced 0037.
"""
from __future__ import annotations

WORLD = "world_adv_0037"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (37 % 8), "biome": ["ash", "crystal", "void", "rift"][37 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
