"""Music ultimate 0333.
"""
from __future__ import annotations

ID = "music_ultimate_0333"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 333}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
