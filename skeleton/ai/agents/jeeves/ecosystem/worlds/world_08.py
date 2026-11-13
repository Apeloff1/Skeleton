"""World pack 08.
"""
from __future__ import annotations

WORLD_ID = "world_08"
BIOME = ["ash", "crystal", "void", "rift", "ember"][8 % 5]

def describe() -> dict:
    return {"id": WORLD_ID, "biome": BIOME, "rooms": 6 + (8 % 5), "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"] if BIOME != "void" else ["wisp", "shade", "boss"]
