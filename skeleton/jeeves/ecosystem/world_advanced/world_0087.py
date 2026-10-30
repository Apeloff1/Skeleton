"""World advanced 0087.
"""
from __future__ import annotations

WORLD = "world_adv_0087"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (87 % 8), "biome": ["ash", "crystal", "void", "rift"][87 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
