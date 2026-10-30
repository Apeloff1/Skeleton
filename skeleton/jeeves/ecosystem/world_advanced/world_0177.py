"""World advanced 0177.
"""
from __future__ import annotations

WORLD = "world_adv_0177"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (177 % 8), "biome": ["ash", "crystal", "void", "rift"][177 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
