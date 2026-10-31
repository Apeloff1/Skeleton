"""Music ultra 0101.
"""
from __future__ import annotations

ID = "music_ultra_0101"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 101}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
