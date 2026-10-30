"""World advanced 0053.
"""
from __future__ import annotations

WORLD = "world_adv_0053"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (53 % 8), "biome": ["ash", "crystal", "void", "rift"][53 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
