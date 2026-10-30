"""World advanced 0119.
"""
from __future__ import annotations

WORLD = "world_adv_0119"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (119 % 8), "biome": ["ash", "crystal", "void", "rift"][119 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
