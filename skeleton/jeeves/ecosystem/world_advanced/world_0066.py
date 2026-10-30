"""World advanced 0066.
"""
from __future__ import annotations

WORLD = "world_adv_0066"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (66 % 8), "biome": ["ash", "crystal", "void", "rift"][66 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
