"""Music supreme 0121.
"""
from __future__ import annotations

ID = "music_supreme_0121"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 121}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
