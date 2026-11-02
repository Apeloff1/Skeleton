"""Pet eco_prime 0160.
"""
from __future__ import annotations

ID = "pet_eco_prime_0160"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 160}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
