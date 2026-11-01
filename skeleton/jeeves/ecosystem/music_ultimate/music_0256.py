"""Music ultimate 0256.
"""
from __future__ import annotations

ID = "music_ultimate_0256"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 256}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
