"""Music scale2 0040.
"""
from __future__ import annotations

ID = "music_scale2_0040"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 40}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
