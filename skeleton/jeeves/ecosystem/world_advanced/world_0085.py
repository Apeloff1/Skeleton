"""World advanced 0085.
"""
from __future__ import annotations

WORLD = "world_adv_0085"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (85 % 8), "biome": ["ash", "crystal", "void", "rift"][85 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
