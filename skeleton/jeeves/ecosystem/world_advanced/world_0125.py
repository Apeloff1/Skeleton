"""World advanced 0125.
"""
from __future__ import annotations

WORLD = "world_adv_0125"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (125 % 8), "biome": ["ash", "crystal", "void", "rift"][125 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
