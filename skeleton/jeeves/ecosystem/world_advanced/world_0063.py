"""World advanced 0063.
"""
from __future__ import annotations

WORLD = "world_adv_0063"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (63 % 8), "biome": ["ash", "crystal", "void", "rift"][63 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
