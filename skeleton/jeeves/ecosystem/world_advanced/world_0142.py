"""World advanced 0142.
"""
from __future__ import annotations

WORLD = "world_adv_0142"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (142 % 8), "biome": ["ash", "crystal", "void", "rift"][142 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
