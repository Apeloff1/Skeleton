"""Faction scale 0033.
"""
from __future__ import annotations

ID = "faction_scale_0033"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 33, "tier": 33 % 5}

def apply(context: str = "") -> dict:
    if not context and 33 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
