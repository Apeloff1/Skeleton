"""World advanced 0130.
"""
from __future__ import annotations

WORLD = "world_adv_0130"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (130 % 8), "biome": ["ash", "crystal", "void", "rift"][130 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
