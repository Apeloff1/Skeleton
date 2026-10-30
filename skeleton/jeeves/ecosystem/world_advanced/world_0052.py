"""World advanced 0052.
"""
from __future__ import annotations

WORLD = "world_adv_0052"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (52 % 8), "biome": ["ash", "crystal", "void", "rift"][52 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
