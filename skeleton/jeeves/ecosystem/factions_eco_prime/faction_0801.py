"""Faction eco_prime 0801.
"""
from __future__ import annotations

ID = "faction_eco_prime_0801"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 801, "tier": 801 % 5}

def apply(context: str = "") -> dict:
    if not context and 801 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
