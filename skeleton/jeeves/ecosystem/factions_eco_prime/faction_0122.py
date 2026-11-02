"""Faction eco_prime 0122.
"""
from __future__ import annotations

ID = "faction_eco_prime_0122"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 122, "tier": 122 % 5}

def apply(context: str = "") -> dict:
    if not context and 122 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
