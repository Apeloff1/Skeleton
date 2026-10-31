"""Faction ultra 0043.
"""
from __future__ import annotations

ID = "faction_ultra_0043"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 43, "tier": 43 % 5}

def apply(context: str = "") -> dict:
    if not context and 43 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
