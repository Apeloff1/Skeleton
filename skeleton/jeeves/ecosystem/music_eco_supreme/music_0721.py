"""Music eco_supreme 0721.
"""
from __future__ import annotations

ID = "music_eco_supreme_0721"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 721}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
