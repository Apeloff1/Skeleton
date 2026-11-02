"""Music eco_apex 0267.
"""
from __future__ import annotations

ID = "music_eco_apex_0267"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 267}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
