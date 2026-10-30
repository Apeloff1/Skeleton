"""Faction scale 0176.
"""
from __future__ import annotations

ID = "faction_scale_0176"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 176, "tier": 176 % 5}

def apply(context: str = "") -> dict:
    if not context and 176 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
