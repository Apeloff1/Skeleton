"""World advanced 0140.
"""
from __future__ import annotations

WORLD = "world_adv_0140"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (140 % 8), "biome": ["ash", "crystal", "void", "rift"][140 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
