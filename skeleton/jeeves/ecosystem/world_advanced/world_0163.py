"""World advanced 0163.
"""
from __future__ import annotations

WORLD = "world_adv_0163"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (163 % 8), "biome": ["ash", "crystal", "void", "rift"][163 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
