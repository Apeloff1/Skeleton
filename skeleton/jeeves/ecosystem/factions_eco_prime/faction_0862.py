"""Faction eco_prime 0862.
"""
from __future__ import annotations

ID = "faction_eco_prime_0862"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 862, "tier": 862 % 5}

def apply(context: str = "") -> dict:
    if not context and 862 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
