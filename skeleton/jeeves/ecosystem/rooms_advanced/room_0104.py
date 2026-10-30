"""Room advanced 0104.
"""
from __future__ import annotations

ID = "room_adv_0104"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 104}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
