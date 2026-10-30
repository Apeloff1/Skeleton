"""World advanced 0172.
"""
from __future__ import annotations

WORLD = "world_adv_0172"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (172 % 8), "biome": ["ash", "crystal", "void", "rift"][172 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
