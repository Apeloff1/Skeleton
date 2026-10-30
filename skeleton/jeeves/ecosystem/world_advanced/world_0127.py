"""World advanced 0127.
"""
from __future__ import annotations

WORLD = "world_adv_0127"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (127 % 8), "biome": ["ash", "crystal", "void", "rift"][127 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
