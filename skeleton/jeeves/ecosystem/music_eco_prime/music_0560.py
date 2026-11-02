"""Music eco_prime 0560.
"""
from __future__ import annotations

ID = "music_eco_prime_0560"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 560}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
