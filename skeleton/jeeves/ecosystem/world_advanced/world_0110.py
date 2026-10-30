"""World advanced 0110.
"""
from __future__ import annotations

WORLD = "world_adv_0110"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (110 % 8), "biome": ["ash", "crystal", "void", "rift"][110 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
