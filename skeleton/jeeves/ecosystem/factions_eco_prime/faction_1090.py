"""Faction eco_prime 1090.
"""
from __future__ import annotations

ID = "faction_eco_prime_1090"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1090, "tier": 1090 % 5}

def apply(context: str = "") -> dict:
    if not context and 1090 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
