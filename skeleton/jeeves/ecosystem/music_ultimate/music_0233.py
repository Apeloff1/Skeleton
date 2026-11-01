"""Music ultimate 0233.
"""
from __future__ import annotations

ID = "music_ultimate_0233"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 233}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
