"""Pet eco_prime 0340.
"""
from __future__ import annotations

ID = "pet_eco_prime_0340"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 340}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
