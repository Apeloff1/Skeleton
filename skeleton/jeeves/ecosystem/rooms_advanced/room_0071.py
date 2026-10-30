"""Room advanced 0071.
"""
from __future__ import annotations

ID = "room_adv_0071"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 71}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
