"""Music eco_apex 0207.
"""
from __future__ import annotations

ID = "music_eco_apex_0207"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 207}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
