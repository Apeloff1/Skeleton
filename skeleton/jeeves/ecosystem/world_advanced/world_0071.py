"""World advanced 0071.
"""
from __future__ import annotations

WORLD = "world_adv_0071"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (71 % 8), "biome": ["ash", "crystal", "void", "rift"][71 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
