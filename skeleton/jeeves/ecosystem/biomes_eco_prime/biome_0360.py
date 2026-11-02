"""Biome eco_prime 0360.
"""
from __future__ import annotations

ID = "biome_eco_prime_0360"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 360, "tier": 360 % 5}

def apply(context: str = "") -> dict:
    if not context and 360 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
