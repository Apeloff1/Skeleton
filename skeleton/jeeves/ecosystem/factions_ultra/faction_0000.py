"""Faction ultra 0000.
"""
from __future__ import annotations

ID = "faction_ultra_0000"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 0, "tier": 0 % 5}

def apply(context: str = "") -> dict:
    if not context and 0 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
