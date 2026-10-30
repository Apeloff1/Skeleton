"""Room advanced 0030.
"""
from __future__ import annotations

ID = "room_adv_0030"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 30}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
