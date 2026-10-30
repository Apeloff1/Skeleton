"""World advanced 0042.
"""
from __future__ import annotations

WORLD = "world_adv_0042"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (42 % 8), "biome": ["ash", "crystal", "void", "rift"][42 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
