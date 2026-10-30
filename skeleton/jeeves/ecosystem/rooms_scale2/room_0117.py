"""Room scale2 0117.
"""
from __future__ import annotations

ID = "room_scale2_0117"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 117}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
