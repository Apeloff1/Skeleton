"""Music max 0099.
"""
from __future__ import annotations

ID = "music_max_0099"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
