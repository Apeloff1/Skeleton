"""Music peak 0174.
"""
from __future__ import annotations

ID = "music_peak_0174"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 174}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
