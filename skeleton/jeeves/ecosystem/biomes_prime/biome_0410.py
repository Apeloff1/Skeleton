"""Biome prime 0410.
"""
from __future__ import annotations

ID = "biome_prime_0410"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 410, "tier": 410 % 5}

def apply(context: str = "") -> dict:
    if not context and 410 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
