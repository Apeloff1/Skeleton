"""Music apex 0125.
"""
from __future__ import annotations

ID = "music_apex_0125"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 125}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
