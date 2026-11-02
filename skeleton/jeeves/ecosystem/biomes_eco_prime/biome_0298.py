"""Biome eco_prime 0298.
"""
from __future__ import annotations

ID = "biome_eco_prime_0298"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 298, "tier": 298 % 5}

def apply(context: str = "") -> dict:
    if not context and 298 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
