"""Music ultimate 0360.
"""
from __future__ import annotations

ID = "music_ultimate_0360"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 360}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
