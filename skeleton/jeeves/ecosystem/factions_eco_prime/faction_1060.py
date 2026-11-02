"""Faction eco_prime 1060.
"""
from __future__ import annotations

ID = "faction_eco_prime_1060"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1060, "tier": 1060 % 5}

def apply(context: str = "") -> dict:
    if not context and 1060 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
