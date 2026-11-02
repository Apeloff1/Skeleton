"""Biome eco_prime 0940.
"""
from __future__ import annotations

ID = "biome_eco_prime_0940"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 940, "tier": 940 % 5}

def apply(context: str = "") -> dict:
    if not context and 940 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
