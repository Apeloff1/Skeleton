"""Room advanced 0099.
"""
from __future__ import annotations

ID = "room_adv_0099"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
