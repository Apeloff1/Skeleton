"""Music ultra 0067.
"""
from __future__ import annotations

ID = "music_ultra_0067"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 67}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
