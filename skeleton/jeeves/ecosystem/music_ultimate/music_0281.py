"""Music ultimate 0281.
"""
from __future__ import annotations

ID = "music_ultimate_0281"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 281}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
