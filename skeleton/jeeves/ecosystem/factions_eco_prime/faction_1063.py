"""Faction eco_prime 1063.
"""
from __future__ import annotations

ID = "faction_eco_prime_1063"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 1063, "tier": 1063 % 5}

def apply(context: str = "") -> dict:
    if not context and 1063 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
