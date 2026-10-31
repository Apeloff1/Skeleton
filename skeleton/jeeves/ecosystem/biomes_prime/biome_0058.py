"""Biome prime 0058.
"""
from __future__ import annotations

ID = "biome_prime_0058"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 58, "tier": 58 % 5}

def apply(context: str = "") -> dict:
    if not context and 58 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
