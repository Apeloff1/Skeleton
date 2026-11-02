"""Music eco_apex 0137.
"""
from __future__ import annotations

ID = "music_eco_apex_0137"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 137}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
