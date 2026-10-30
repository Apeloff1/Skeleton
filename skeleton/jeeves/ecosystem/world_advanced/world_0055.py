"""World advanced 0055.
"""
from __future__ import annotations

WORLD = "world_adv_0055"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (55 % 8), "biome": ["ash", "crystal", "void", "rift"][55 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
