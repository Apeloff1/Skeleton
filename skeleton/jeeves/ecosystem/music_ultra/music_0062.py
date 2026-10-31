"""Music ultra 0062.
"""
from __future__ import annotations

ID = "music_ultra_0062"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 62}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
