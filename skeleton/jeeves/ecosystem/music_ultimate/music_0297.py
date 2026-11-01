"""Music ultimate 0297.
"""
from __future__ import annotations

ID = "music_ultimate_0297"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 297}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
