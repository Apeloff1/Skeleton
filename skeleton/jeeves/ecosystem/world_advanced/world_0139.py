"""World advanced 0139.
"""
from __future__ import annotations

WORLD = "world_adv_0139"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (139 % 8), "biome": ["ash", "crystal", "void", "rift"][139 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
