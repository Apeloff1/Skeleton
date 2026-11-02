"""Pet eco_prime 0207.
"""
from __future__ import annotations

ID = "pet_eco_prime_0207"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 207}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
