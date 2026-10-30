"""Room scale2 0145.
"""
from __future__ import annotations

ID = "room_scale2_0145"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 145}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
