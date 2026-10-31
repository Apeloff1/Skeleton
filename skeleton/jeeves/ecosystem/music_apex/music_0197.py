"""Music apex 0197.
"""
from __future__ import annotations

ID = "music_apex_0197"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 197}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
