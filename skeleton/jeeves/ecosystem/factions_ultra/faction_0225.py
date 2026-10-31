"""Faction ultra 0225.
"""
from __future__ import annotations

ID = "faction_ultra_0225"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 225, "tier": 225 % 5}

def apply(context: str = "") -> dict:
    if not context and 225 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
