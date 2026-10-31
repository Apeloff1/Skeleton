"""Biome prime 0393.
"""
from __future__ import annotations

ID = "biome_prime_0393"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 393, "tier": 393 % 5}

def apply(context: str = "") -> dict:
    if not context and 393 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
