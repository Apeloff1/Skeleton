"""Music mega 0063.
"""
from __future__ import annotations

ID = "music_mega_0063"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 63}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
