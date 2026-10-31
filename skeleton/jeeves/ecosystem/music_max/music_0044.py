"""Music max 0044.
"""
from __future__ import annotations

ID = "music_max_0044"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 44}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
