"""World advanced 0171.
"""
from __future__ import annotations

WORLD = "world_adv_0171"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (171 % 8), "biome": ["ash", "crystal", "void", "rift"][171 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
