"""World advanced 0115.
"""
from __future__ import annotations

WORLD = "world_adv_0115"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (115 % 8), "biome": ["ash", "crystal", "void", "rift"][115 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
