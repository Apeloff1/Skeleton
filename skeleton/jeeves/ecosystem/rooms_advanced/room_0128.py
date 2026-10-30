"""Room advanced 0128.
"""
from __future__ import annotations

ID = "room_adv_0128"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 128}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
