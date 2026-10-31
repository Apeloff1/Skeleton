"""Faction ultra 0285.
"""
from __future__ import annotations

ID = "faction_ultra_0285"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 285, "tier": 285 % 5}

def apply(context: str = "") -> dict:
    if not context and 285 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
