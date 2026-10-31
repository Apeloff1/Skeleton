"""Music prime 0180.
"""
from __future__ import annotations

ID = "music_prime_0180"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 180}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
