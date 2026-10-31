"""Biome prime 0481.
"""
from __future__ import annotations

ID = "biome_prime_0481"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 481, "tier": 481 % 5}

def apply(context: str = "") -> dict:
    if not context and 481 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
