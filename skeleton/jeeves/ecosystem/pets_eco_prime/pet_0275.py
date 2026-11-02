"""Pet eco_prime 0275.
"""
from __future__ import annotations

ID = "pet_eco_prime_0275"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 275}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
