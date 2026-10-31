"""Music apex 0189.
"""
from __future__ import annotations

ID = "music_apex_0189"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 189}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
