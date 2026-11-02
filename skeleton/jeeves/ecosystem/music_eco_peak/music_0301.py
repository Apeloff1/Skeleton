"""Music eco_peak 0301.
"""
from __future__ import annotations

ID = "music_eco_peak_0301"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 301}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
