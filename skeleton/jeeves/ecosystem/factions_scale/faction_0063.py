"""Faction scale 0063.
"""
from __future__ import annotations

ID = "faction_scale_0063"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 63, "tier": 63 % 5}

def apply(context: str = "") -> dict:
    if not context and 63 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
