"""World advanced 0083.
"""
from __future__ import annotations

WORLD = "world_adv_0083"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (83 % 8), "biome": ["ash", "crystal", "void", "rift"][83 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
