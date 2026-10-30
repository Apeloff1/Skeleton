"""World advanced 0072.
"""
from __future__ import annotations

WORLD = "world_adv_0072"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (72 % 8), "biome": ["ash", "crystal", "void", "rift"][72 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
