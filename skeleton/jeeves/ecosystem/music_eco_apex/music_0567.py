"""Music eco_apex 0567.
"""
from __future__ import annotations

ID = "music_eco_apex_0567"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 567}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
