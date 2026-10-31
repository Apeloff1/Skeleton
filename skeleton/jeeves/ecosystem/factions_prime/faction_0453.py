"""Faction prime 0453.
"""
from __future__ import annotations

ID = "faction_prime_0453"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 453, "tier": 453 % 5}

def apply(context: str = "") -> dict:
    if not context and 453 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
