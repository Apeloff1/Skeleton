"""Music ultimate 0228.
"""
from __future__ import annotations

ID = "music_ultimate_0228"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 228}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
