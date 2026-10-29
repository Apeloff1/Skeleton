"""Room template 0088.
"""
from __future__ import annotations

ROOM = "room_0088"
KIND = ["combat", "shop", "rest", "boss"][88 % 4]

def layout() -> dict:
    return {"id": ROOM, "kind": KIND, "exits": ["n", "e"] if KIND != "boss" else ["s"]}

def spawn_count() -> int:
    return 0 if KIND in ("shop", "rest") else (1 if KIND == "boss" else 3)
