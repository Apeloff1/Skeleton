"""World advanced 0106.
"""
from __future__ import annotations

WORLD = "world_adv_0106"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (106 % 8), "biome": ["ash", "crystal", "void", "rift"][106 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
