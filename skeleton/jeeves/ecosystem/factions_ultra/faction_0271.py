"""Faction ultra 0271.
"""
from __future__ import annotations

ID = "faction_ultra_0271"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 271, "tier": 271 % 5}

def apply(context: str = "") -> dict:
    if not context and 271 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
