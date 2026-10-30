"""Room scale2 0133.
"""
from __future__ import annotations

ID = "room_scale2_0133"

def describe() -> dict:
    return {"id": ID, "kind": "room", "index": 133}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
