"""Music peak 0133.
"""
from __future__ import annotations

ID = "music_peak_0133"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 133}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
