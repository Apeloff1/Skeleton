"""World advanced 0158.
"""
from __future__ import annotations

WORLD = "world_adv_0158"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (158 % 8), "biome": ["ash", "crystal", "void", "rift"][158 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
