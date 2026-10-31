"""Faction prime 0332.
"""
from __future__ import annotations

ID = "faction_prime_0332"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 332, "tier": 332 % 5}

def apply(context: str = "") -> dict:
    if not context and 332 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
