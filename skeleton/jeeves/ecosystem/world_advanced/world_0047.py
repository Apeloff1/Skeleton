"""World advanced 0047.
"""
from __future__ import annotations

WORLD = "world_adv_0047"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (47 % 8), "biome": ["ash", "crystal", "void", "rift"][47 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
