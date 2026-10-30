"""World advanced 0165.
"""
from __future__ import annotations

WORLD = "world_adv_0165"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (165 % 8), "biome": ["ash", "crystal", "void", "rift"][165 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
