"""World advanced 0062.
"""
from __future__ import annotations

WORLD = "world_adv_0062"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (62 % 8), "biome": ["ash", "crystal", "void", "rift"][62 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
