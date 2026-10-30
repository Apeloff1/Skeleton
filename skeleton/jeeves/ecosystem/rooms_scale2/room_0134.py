"""Room scale2 0134.
"""
from __future__ import annotations

ID = "room_scale2_0134"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 134}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
