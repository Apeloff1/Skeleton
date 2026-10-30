"""Music mega 0099.
"""
from __future__ import annotations

ID = "music_mega_0099"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
