"""Faction eco_prime 0867.
"""
from __future__ import annotations

ID = "faction_eco_prime_0867"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 867, "tier": 867 % 5}

def apply(context: str = "") -> dict:
    if not context and 867 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
