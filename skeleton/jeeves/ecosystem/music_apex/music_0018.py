"""Music apex 0018.
"""
from __future__ import annotations

ID = "music_apex_0018"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 18}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
