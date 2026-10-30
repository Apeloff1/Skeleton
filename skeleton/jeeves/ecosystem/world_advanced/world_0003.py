"""World advanced 0003.
"""
from __future__ import annotations

WORLD = "world_adv_0003"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (3 % 8), "biome": ["ash", "crystal", "void", "rift"][3 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
