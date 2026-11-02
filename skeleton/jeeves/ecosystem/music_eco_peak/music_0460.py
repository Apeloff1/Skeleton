"""Music eco_peak 0460.
"""
from __future__ import annotations

ID = "music_eco_peak_0460"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 460}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
