"""Faction scale 0065.
"""
from __future__ import annotations

ID = "faction_scale_0065"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 65, "tier": 65 % 5}

def apply(context: str = "") -> dict:
    if not context and 65 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
