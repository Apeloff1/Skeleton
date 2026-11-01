"""Music supreme 0208.
"""
from __future__ import annotations

ID = "music_supreme_0208"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 208}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
