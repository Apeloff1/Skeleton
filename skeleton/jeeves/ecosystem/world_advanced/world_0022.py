"""World advanced 0022.
"""
from __future__ import annotations

WORLD = "world_adv_0022"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (22 % 8), "biome": ["ash", "crystal", "void", "rift"][22 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
