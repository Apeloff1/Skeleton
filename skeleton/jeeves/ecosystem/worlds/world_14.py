"""World pack 14.
"""
from __future__ import annotations

WORLD_ID = "world_14"
BIOME = ["ash", "crystal", "void", "rift", "ember"][14 % 5]

def describe() -> dict:
    return {"id": WORLD_ID, "biome": BIOME, "rooms": 6 + (14 % 5), "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"] if BIOME != "void" else ["wisp", "shade", "boss"]
