"""World advanced 0169.
"""
from __future__ import annotations

WORLD = "world_adv_0169"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (169 % 8), "biome": ["ash", "crystal", "void", "rift"][169 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
