"""Music ultimate 0375.
"""
from __future__ import annotations

ID = "music_ultimate_0375"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 375}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
