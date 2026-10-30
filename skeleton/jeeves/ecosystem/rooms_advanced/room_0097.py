"""Room advanced 0097.
"""
from __future__ import annotations

ID = "room_adv_0097"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 97}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
