"""World pack 03.
"""
from __future__ import annotations

WORLD_ID = "world_03"
BIOME = ["ash", "crystal", "void", "rift", "ember"][3 % 5]

def describe() -> dict:
    return {"id": WORLD_ID, "biome": BIOME, "rooms": 6 + (3 % 5), "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"] if BIOME != "void" else ["wisp", "shade", "boss"]
