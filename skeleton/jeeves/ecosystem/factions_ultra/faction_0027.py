"""Faction ultra 0027.
"""
from __future__ import annotations

ID = "faction_ultra_0027"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 27, "tier": 27 % 5}

def apply(context: str = "") -> dict:
    if not context and 27 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
