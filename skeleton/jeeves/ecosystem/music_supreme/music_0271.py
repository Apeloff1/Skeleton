"""Music supreme 0271.
"""
from __future__ import annotations

ID = "music_supreme_0271"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 271}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
