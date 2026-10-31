"""Music apex 0175.
"""
from __future__ import annotations

ID = "music_apex_0175"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 175}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
