"""Music eco_prime 0102.
"""
from __future__ import annotations

ID = "music_eco_prime_0102"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 102}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
