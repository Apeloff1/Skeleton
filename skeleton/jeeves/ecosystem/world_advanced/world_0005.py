"""World advanced 0005.
"""
from __future__ import annotations

WORLD = "world_adv_0005"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (5 % 8), "biome": ["ash", "crystal", "void", "rift"][5 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
