"""Faction max 0257.
"""
from __future__ import annotations

ID = "faction_max_0257"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 257, "tier": 257 % 5}

def apply(context: str = "") -> dict:
    if not context and 257 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
