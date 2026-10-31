"""Faction ultra 0216.
"""
from __future__ import annotations

ID = "faction_ultra_0216"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 216, "tier": 216 % 5}

def apply(context: str = "") -> dict:
    if not context and 216 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
