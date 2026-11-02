"""Biome eco_prime 0250.
"""
from __future__ import annotations

ID = "biome_eco_prime_0250"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 250, "tier": 250 % 5}

def apply(context: str = "") -> dict:
    if not context and 250 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
