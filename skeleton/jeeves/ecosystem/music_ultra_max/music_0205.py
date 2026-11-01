"""Music ultra_max 0205.
"""
from __future__ import annotations

ID = "music_ultra_max_0205"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 205}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
