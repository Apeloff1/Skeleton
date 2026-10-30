"""World advanced 0038.
"""
from __future__ import annotations

WORLD = "world_adv_0038"

def describe() -> dict:
    return {"id": WORLD, "rooms": 6 + (38 % 8), "biome": ["ash", "crystal", "void", "rift"][38 % 4], "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"]
