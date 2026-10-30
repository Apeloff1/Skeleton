"""World advanced 0065.
"""
from __future__ import annotations

WORLD = "world_adv_0065"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (65 % 8), "biome": ["ash", "crystal", "void", "rift"][65 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
