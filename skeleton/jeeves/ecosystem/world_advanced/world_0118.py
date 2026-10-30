"""World advanced 0118.
"""
from __future__ import annotations

WORLD = "world_adv_0118"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (118 % 8), "biome": ["ash", "crystal", "void", "rift"][118 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
