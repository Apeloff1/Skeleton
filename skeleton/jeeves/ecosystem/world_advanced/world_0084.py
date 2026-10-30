"""World advanced 0084.
"""
from __future__ import annotations

WORLD = "world_adv_0084"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (84 % 8), "biome": ["ash", "crystal", "void", "rift"][84 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
