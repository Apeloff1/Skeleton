"""Faction prime 0418.
"""
from __future__ import annotations

ID = "faction_prime_0418"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 418, "tier": 418 % 5}

def apply(context: str = "") -> dict:
    if not context and 418 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
