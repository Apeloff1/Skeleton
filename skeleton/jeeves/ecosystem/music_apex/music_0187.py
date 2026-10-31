"""Music apex 0187.
"""
from __future__ import annotations

ID = "music_apex_0187"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 187}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
