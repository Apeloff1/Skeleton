"""Music eco_prime 0000.
"""
from __future__ import annotations

ID = "music_eco_prime_0000"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 0}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
