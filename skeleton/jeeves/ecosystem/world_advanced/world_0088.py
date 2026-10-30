"""World advanced 0088.
"""
from __future__ import annotations

WORLD = "world_adv_0088"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (88 % 8), "biome": ["ash", "crystal", "void", "rift"][88 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
