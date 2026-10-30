"""World advanced 0123.
"""
from __future__ import annotations

WORLD = "world_adv_0123"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (123 % 8), "biome": ["ash", "crystal", "void", "rift"][123 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
