"""Biome eco_prime 0796.
"""
from __future__ import annotations

ID = "biome_eco_prime_0796"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 796, "tier": 796 % 5}

def apply(context: str = "") -> dict:
    if not context and 796 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
