"""Faction scale 0090.
"""
from __future__ import annotations

ID = "faction_scale_0090"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 90, "tier": 90 % 5}

def apply(context: str = "") -> dict:
    if not context and 90 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
