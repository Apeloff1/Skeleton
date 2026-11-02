"""Biome eco_prime 0718.
"""
from __future__ import annotations

ID = "biome_eco_prime_0718"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 718, "tier": 718 % 5}

def apply(context: str = "") -> dict:
    if not context and 718 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
