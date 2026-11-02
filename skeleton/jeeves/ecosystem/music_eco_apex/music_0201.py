"""Music eco_apex 0201.
"""
from __future__ import annotations

ID = "music_eco_apex_0201"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 201}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
