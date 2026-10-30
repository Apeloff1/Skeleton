"""Faction scale 0058.
"""
from __future__ import annotations

ID = "faction_scale_0058"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 58, "tier": 58 % 5}

def apply(context: str = "") -> dict:
    if not context and 58 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
