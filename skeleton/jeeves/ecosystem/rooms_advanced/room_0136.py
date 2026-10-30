"""Room advanced 0136.
"""
from __future__ import annotations

ID = "room_adv_0136"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 136}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
