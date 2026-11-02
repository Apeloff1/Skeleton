"""Music eco_apex 0017.
"""
from __future__ import annotations

ID = "music_eco_apex_0017"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 17}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
