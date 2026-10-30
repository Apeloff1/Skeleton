"""Faction scale 0173.
"""
from __future__ import annotations

ID = "faction_scale_0173"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 173, "tier": 173 % 5}

def apply(context: str = "") -> dict:
    if not context and 173 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
