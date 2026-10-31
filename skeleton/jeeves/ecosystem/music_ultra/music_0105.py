"""Music ultra 0105.
"""
from __future__ import annotations

ID = "music_ultra_0105"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 105}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
