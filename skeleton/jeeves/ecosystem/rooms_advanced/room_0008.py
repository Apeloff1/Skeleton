"""Room advanced 0008.
"""
from __future__ import annotations

ID = "room_adv_0008"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 8}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
