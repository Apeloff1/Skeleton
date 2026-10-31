"""Music apex 0183.
"""
from __future__ import annotations

ID = "music_apex_0183"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 183}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
