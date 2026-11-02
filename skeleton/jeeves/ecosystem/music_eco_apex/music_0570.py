"""Music eco_apex 0570.
"""
from __future__ import annotations

ID = "music_eco_apex_0570"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 570}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
