"""Faction max 0325.
"""
from __future__ import annotations

ID = "faction_max_0325"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 325, "tier": 325 % 5}

def apply(context: str = "") -> dict:
    if not context and 325 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
