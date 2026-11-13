"""World pack 07.
"""
from __future__ import annotations

WORLD_ID = "world_07"
BIOME = ["ash", "crystal", "void", "rift", "ember"][7 % 5]

def describe() -> dict:
    return {"id": WORLD_ID, "biome": BIOME, "rooms": 6 + (7 % 5), "boss": True}

def spawn_table() -> list[str]:
    return ["grunt", "elite", "boss"] if BIOME != "void" else ["wisp", "shade", "boss"]
