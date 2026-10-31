"""Biome prime 0428.
"""
from __future__ import annotations

ID = "biome_prime_0428"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 428, "tier": 428 % 5}

def apply(context: str = "") -> dict:
    if not context and 428 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
