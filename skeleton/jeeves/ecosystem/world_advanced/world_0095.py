"""World advanced 0095.
"""
from __future__ import annotations

WORLD = "world_adv_0095"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (95 % 8), "biome": ["ash", "crystal", "void", "rift"][95 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
