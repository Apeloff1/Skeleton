"""Music ultimate 0263.
"""
from __future__ import annotations

ID = "music_ultimate_0263"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 263}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
