"""World advanced 0103.
"""
from __future__ import annotations

WORLD = "world_adv_0103"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (103 % 8), "biome": ["ash", "crystal", "void", "rift"][103 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
