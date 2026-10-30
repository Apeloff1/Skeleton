"""World advanced 0045.
"""
from __future__ import annotations

WORLD = "world_adv_0045"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (45 % 8), "biome": ["ash", "crystal", "void", "rift"][45 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
