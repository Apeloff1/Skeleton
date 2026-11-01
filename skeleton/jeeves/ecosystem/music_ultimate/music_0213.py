"""Music ultimate 0213.
"""
from __future__ import annotations

ID = "music_ultimate_0213"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 213}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
