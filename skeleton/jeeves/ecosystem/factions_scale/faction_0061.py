"""Faction scale 0061.
"""
from __future__ import annotations

ID = "faction_scale_0061"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 61, "tier": 61 % 5}

def apply(context: str = "") -> dict:
    if not context and 61 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
