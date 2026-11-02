"""Pet eco_prime 0381.
"""
from __future__ import annotations

ID = "pet_eco_prime_0381"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 381}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
