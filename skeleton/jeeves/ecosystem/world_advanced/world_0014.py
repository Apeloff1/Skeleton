"""World advanced 0014.
"""
from __future__ import annotations

WORLD = "world_adv_0014"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (14 % 8), "biome": ["ash", "crystal", "void", "rift"][14 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
