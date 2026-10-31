"""Music ultra 0113.
"""
from __future__ import annotations

ID = "music_ultra_0113"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 113}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
