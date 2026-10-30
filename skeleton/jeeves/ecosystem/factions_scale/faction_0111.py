"""Faction scale 0111.
"""
from __future__ import annotations

ID = "faction_scale_0111"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 111, "tier": 111 % 5}

def apply(context: str = "") -> dict:
    if not context and 111 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
