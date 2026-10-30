"""World advanced 0026.
"""
from __future__ import annotations

WORLD = "world_adv_0026"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (26 % 8), "biome": ["ash", "crystal", "void", "rift"][26 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
