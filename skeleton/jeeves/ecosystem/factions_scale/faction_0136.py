"""Faction scale 0136.
"""
from __future__ import annotations

ID = "faction_scale_0136"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 136, "tier": 136 % 5}

def apply(context: str = "") -> dict:
    if not context and 136 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
