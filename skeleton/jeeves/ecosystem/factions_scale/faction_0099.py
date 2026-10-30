"""Faction scale 0099.
"""
from __future__ import annotations

ID = "faction_scale_0099"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 99, "tier": 99 % 5}

def apply(context: str = "") -> dict:
    if not context and 99 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
