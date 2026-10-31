"""World pack 09.
"""
from __future__ import annotations

WORLD_ID = "world_09"
BIOME = ["ash", "crystal", "void", "rift", "ember"][9 % 5]

def describe() -> dict:
    return {"id": WORLD_ID, "biome": BIOME, "rooms": 6 + (9 % 5), "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"] if BIOME != "void" else ["wisp", "shade", "boss"]
