"""Faction scale 0197.
"""
from __future__ import annotations

ID = "faction_scale_0197"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 197, "tier": 197 % 5}

def apply(context: str = "") -> dict:
    if not context and 197 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
