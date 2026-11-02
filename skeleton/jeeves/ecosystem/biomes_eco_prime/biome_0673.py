"""Biome eco_prime 0673.
"""
from __future__ import annotations

ID = "biome_eco_prime_0673"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 673, "tier": 673 % 5}

def apply(context: str = "") -> dict:
    if not context and 673 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
