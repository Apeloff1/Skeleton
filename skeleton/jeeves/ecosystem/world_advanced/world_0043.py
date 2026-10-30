"""World advanced 0043.
"""
from __future__ import annotations

WORLD = "world_adv_0043"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (43 % 8), "biome": ["ash", "crystal", "void", "rift"][43 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
