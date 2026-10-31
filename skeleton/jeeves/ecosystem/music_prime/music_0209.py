"""Music prime 0209.
"""
from __future__ import annotations

ID = "music_prime_0209"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 209}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
