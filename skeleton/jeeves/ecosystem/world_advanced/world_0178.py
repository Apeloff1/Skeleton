"""World advanced 0178.
"""
from __future__ import annotations

WORLD = "world_adv_0178"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (178 % 8), "biome": ["ash", "crystal", "void", "rift"][178 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
