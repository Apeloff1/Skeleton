"""Music ultra_max 0218.
"""
from __future__ import annotations

ID = "music_ultra_max_0218"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 218}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
