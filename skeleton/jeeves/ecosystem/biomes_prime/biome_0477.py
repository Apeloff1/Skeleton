"""Biome prime 0477.
"""
from __future__ import annotations

ID = "biome_prime_0477"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 477, "tier": 477 % 5}

def apply(context: str = "") -> dict:
    if not context and 477 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
