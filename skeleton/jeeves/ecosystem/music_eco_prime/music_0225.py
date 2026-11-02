"""Music eco_prime 0225.
"""
from __future__ import annotations

ID = "music_eco_prime_0225"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 225}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
