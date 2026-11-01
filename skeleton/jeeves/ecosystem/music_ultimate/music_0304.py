"""Music ultimate 0304.
"""
from __future__ import annotations

ID = "music_ultimate_0304"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 304}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
