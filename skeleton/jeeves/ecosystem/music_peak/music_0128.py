"""Music peak 0128.
"""
from __future__ import annotations

ID = "music_peak_0128"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 128}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
