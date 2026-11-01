"""Music ultimate 0268.
"""
from __future__ import annotations

ID = "music_ultimate_0268"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 268}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
