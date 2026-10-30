"""World advanced 0108.
"""
from __future__ import annotations

WORLD = "world_adv_0108"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (108 % 8), "biome": ["ash", "crystal", "void", "rift"][108 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
