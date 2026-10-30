"""Faction scale 0199.
"""
from __future__ import annotations

ID = "faction_scale_0199"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 199, "tier": 199 % 5}

def apply(context: str = "") -> dict:
    if not context and 199 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
