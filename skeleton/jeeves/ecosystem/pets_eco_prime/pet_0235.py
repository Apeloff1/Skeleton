"""Pet eco_prime 0235.
"""
from __future__ import annotations

ID = "pet_eco_prime_0235"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 235}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
