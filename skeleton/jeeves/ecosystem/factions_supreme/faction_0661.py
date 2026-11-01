"""Faction supreme 0661.
"""
from __future__ import annotations

ID = "faction_supreme_0661"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 661, "tier": 661 % 5}

def apply(context: str = "") -> dict:
    if not context and 661 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
