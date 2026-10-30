"""Room advanced 0129.
"""
from __future__ import annotations

ID = "room_adv_0129"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 129}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
