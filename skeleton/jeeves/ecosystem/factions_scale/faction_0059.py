"""Faction scale 0059.
"""
from __future__ import annotations

ID = "faction_scale_0059"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 59, "tier": 59 % 5}

def apply(context: str = "") -> dict:
    if not context and 59 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
