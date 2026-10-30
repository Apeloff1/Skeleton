"""Faction scale 0188.
"""
from __future__ import annotations

ID = "faction_scale_0188"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 188, "tier": 188 % 5}

def apply(context: str = "") -> dict:
    if not context and 188 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
