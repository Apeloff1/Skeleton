"""World advanced 0141.
"""
from __future__ import annotations

WORLD = "world_adv_0141"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (141 % 8), "biome": ["ash", "crystal", "void", "rift"][141 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
