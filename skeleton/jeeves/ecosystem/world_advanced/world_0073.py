"""World advanced 0073.
"""
from __future__ import annotations

WORLD = "world_adv_0073"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (73 % 8), "biome": ["ash", "crystal", "void", "rift"][73 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
