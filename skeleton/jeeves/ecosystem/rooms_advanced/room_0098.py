"""Room advanced 0098.
"""
from __future__ import annotations

ID = "room_adv_0098"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 98}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
