"""Faction ultra 0021.
"""
from __future__ import annotations

ID = "faction_ultra_0021"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 21, "tier": 21 % 5}

def apply(context: str = "") -> dict:
    if not context and 21 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
