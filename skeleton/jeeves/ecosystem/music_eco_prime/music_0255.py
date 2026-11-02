"""Music eco_prime 0255.
"""
from __future__ import annotations

ID = "music_eco_prime_0255"

def describe() -> dict:
    return {"id": ID, "kind": "music", "index": 255}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
