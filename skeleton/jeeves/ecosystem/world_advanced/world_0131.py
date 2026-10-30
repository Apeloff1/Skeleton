"""World advanced 0131.
"""
from __future__ import annotations

WORLD = "world_adv_0131"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (131 % 8), "biome": ["ash", "crystal", "void", "rift"][131 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
