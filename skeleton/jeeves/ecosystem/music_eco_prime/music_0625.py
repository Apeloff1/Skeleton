"""Music eco_prime 0625.
"""
from __future__ import annotations

ID = "music_eco_prime_0625"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 625}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
