"""Room advanced 0126.
"""
from __future__ import annotations

ID = "room_adv_0126"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 126}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
