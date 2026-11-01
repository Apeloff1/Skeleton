"""Music ultra_max 0248.
"""
from __future__ import annotations

ID = "music_ultra_max_0248"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 248}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
