"""Music eco_apex 0307.
"""
from __future__ import annotations

ID = "music_eco_apex_0307"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 307}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
