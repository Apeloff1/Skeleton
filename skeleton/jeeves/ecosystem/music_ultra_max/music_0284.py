"""Music ultra_max 0284.
"""
from __future__ import annotations

ID = "music_ultra_max_0284"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 284}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
