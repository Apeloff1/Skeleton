"""World advanced 0031.
"""
from __future__ import annotations

WORLD = "world_adv_0031"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (31 % 8), "biome": ["ash", "crystal", "void", "rift"][31 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
