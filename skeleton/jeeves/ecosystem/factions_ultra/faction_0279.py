"""Faction ultra 0279.
"""
from __future__ import annotations

ID = "faction_ultra_0279"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 279, "tier": 279 % 5}

def apply(context: str = "") -> dict:
    if not context and 279 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
