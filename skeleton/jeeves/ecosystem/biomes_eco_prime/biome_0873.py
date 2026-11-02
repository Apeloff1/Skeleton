"""Biome eco_prime 0873.
"""
from __future__ import annotations

ID = "biome_eco_prime_0873"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 873, "tier": 873 % 5}

def apply(context: str = "") -> dict:
    if not context and 873 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
