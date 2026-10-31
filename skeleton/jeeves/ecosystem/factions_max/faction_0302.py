"""Faction max 0302.
"""
from __future__ import annotations

ID = "faction_max_0302"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 302, "tier": 302 % 5}

def apply(context: str = "") -> dict:
    if not context and 302 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
