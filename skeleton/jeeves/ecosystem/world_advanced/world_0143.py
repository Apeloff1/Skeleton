"""World advanced 0143.
"""
from __future__ import annotations

WORLD = "world_adv_0143"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (143 % 8), "biome": ["ash", "crystal", "void", "rift"][143 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
