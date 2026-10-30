"""World advanced 0135.
"""
from __future__ import annotations

WORLD = "world_adv_0135"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (135 % 8), "biome": ["ash", "crystal", "void", "rift"][135 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
