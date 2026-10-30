"""World advanced 0174.
"""
from __future__ import annotations

WORLD = "world_adv_0174"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (174 % 8), "biome": ["ash", "crystal", "void", "rift"][174 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
