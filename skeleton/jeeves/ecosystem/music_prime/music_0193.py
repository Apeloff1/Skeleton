"""Music prime 0193.
"""
from __future__ import annotations

ID = "music_prime_0193"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 193}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
