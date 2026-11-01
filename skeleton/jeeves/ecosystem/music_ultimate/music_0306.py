"""Music ultimate 0306.
"""
from __future__ import annotations

ID = "music_ultimate_0306"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 306}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
