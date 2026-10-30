"""World advanced 0105.
"""
from __future__ import annotations

WORLD = "world_adv_0105"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (105 % 8), "biome": ["ash", "crystal", "void", "rift"][105 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
