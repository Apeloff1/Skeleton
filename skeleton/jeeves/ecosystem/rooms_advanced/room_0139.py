"""Room advanced 0139.
"""
from __future__ import annotations

ID = "room_adv_0139"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 139}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
