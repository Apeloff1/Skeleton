"""Music eco_apex 0299.
"""
from __future__ import annotations

ID = "music_eco_apex_0299"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 299}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
