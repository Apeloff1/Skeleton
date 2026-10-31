"""Music max 0135.
"""
from __future__ import annotations

ID = "music_max_0135"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 135}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
