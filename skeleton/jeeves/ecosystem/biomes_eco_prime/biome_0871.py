"""Biome eco_prime 0871.
"""
from __future__ import annotations

ID = "biome_eco_prime_0871"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 871, "tier": 871 % 5}

def apply(context: str = "") -> dict:
    if not context and 871 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
