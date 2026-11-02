"""Faction eco_prime 0833.
"""
from __future__ import annotations

ID = "faction_eco_prime_0833"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 833, "tier": 833 % 5}

def apply(context: str = "") -> dict:
    if not context and 833 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
