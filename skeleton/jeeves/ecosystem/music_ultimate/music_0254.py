"""Music ultimate 0254.
"""
from __future__ import annotations

ID = "music_ultimate_0254"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 254}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
