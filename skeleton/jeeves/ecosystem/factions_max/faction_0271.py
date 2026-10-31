"""Faction max 0271.
"""
from __future__ import annotations

ID = "faction_max_0271"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 271, "tier": 271 % 5}

def apply(context: str = "") -> dict:
    if not context and 271 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
