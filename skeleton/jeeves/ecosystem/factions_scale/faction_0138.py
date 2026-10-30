"""Faction scale 0138.
"""
from __future__ import annotations

ID = "faction_scale_0138"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 138, "tier": 138 % 5}

def apply(context: str = "") -> dict:
    if not context and 138 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
