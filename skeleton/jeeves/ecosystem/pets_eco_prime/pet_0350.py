"""Pet eco_prime 0350.
"""
from __future__ import annotations

ID = "pet_eco_prime_0350"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 350}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
