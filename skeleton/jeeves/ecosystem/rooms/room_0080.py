"""Room template 0080.
"""
from __future__ import annotations

ROOM = "room_0080"
KIND = ["combat", "shop", "rest", "boss"][80 % 4]

def layout() -> dict:
    return {"id": ROOM, "kind": KIND, "exits": ["n", "e"] if KIND != "boss" else ["s"]}

def spawn_count() -> int:
    return 0 if KIND in ("shop", "rest") else (1 if KIND == "boss" else 3)
