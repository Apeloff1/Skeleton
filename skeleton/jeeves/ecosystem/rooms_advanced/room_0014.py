"""Room advanced 0014.
"""
from __future__ import annotations

ID = "room_adv_0014"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 14}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
