"""Biome eco_prime 0717.
"""
from __future__ import annotations

ID = "biome_eco_prime_0717"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 717, "tier": 717 % 5}

def apply(context: str = "") -> dict:
    if not context and 717 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
