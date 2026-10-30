"""Faction scale 0119.
"""
from __future__ import annotations

ID = "faction_scale_0119"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 119, "tier": 119 % 5}

def apply(context: str = "") -> dict:
    if not context and 119 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
