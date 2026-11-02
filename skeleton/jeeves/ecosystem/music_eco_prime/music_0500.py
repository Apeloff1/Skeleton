"""Music eco_prime 0500.
"""
from __future__ import annotations

ID = "music_eco_prime_0500"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 500}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
