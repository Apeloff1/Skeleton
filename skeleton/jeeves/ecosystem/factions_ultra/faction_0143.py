"""Faction ultra 0143.
"""
from __future__ import annotations

ID = "faction_ultra_0143"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 143, "tier": 143 % 5}

def apply(context: str = "") -> dict:
    if not context and 143 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
