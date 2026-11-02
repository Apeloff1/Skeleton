"""Biome eco_prime 0900.
"""
from __future__ import annotations

ID = "biome_eco_prime_0900"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 900, "tier": 900 % 5}

def apply(context: str = "") -> dict:
    if not context and 900 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
