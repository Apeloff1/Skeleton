"""World advanced 0148.
"""
from __future__ import annotations

WORLD = "world_adv_0148"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (148 % 8), "biome": ["ash", "crystal", "void", "rift"][148 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
