"""Music eco_prime 0620.
"""
from __future__ import annotations

ID = "music_eco_prime_0620"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 620}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
