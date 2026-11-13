"""World pack 13.
"""
from __future__ import annotations

WORLD_ID = "world_13"
BIOME = ["ash", "crystal", "void", "rift", "ember"][13 % 5]

def describe() -> dict:
    return {"id": WORLD_ID, "biome": BIOME, "rooms": 6 + (13 % 5), "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"] if BIOME != "void" else ["wisp", "shade", "boss"]
