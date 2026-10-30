"""World advanced 0175.
"""
from __future__ import annotations

WORLD = "world_adv_0175"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (175 % 8), "biome": ["ash", "crystal", "void", "rift"][175 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
