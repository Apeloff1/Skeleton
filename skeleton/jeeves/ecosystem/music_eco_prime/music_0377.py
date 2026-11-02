"""Music eco_prime 0377.
"""
from __future__ import annotations

ID = "music_eco_prime_0377"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 377}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
