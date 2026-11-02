"""Music eco_peak 0204.
"""
from __future__ import annotations

ID = "music_eco_peak_0204"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 204}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
