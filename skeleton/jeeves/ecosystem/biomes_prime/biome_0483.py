"""Biome prime 0483.
"""
from __future__ import annotations

ID = "biome_prime_0483"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 483, "tier": 483 % 5}

def apply(context: str = "") -> dict:
    if not context and 483 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
