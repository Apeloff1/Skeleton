"""Music max 0072.
"""
from __future__ import annotations

ID = "music_max_0072"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 72}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
