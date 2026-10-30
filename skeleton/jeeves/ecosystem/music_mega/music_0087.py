"""Music mega 0087.
"""
from __future__ import annotations

ID = "music_mega_0087"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 87}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
