"""World advanced 0076.
"""
from __future__ import annotations

WORLD = "world_adv_0076"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (76 % 8), "biome": ["ash", "crystal", "void", "rift"][76 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
