"""Music peak 0126.
"""
from __future__ import annotations

ID = "music_peak_0126"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 126}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
