"""Room advanced 0003.
"""
from __future__ import annotations

ID = "room_adv_0003"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 3}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
