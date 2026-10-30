"""World advanced 0149.
"""
from __future__ import annotations

WORLD = "world_adv_0149"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (149 % 8), "biome": ["ash", "crystal", "void", "rift"][149 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
