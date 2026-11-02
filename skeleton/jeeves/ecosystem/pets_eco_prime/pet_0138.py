"""Pet eco_prime 0138.
"""
from __future__ import annotations

ID = "pet_eco_prime_0138"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 138}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
