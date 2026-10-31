"""Biome prime 0143.
"""
from __future__ import annotations

ID = "biome_prime_0143"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 143, "tier": 143 % 5}

def apply(context: str = "") -> dict:
    if not context and 143 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
