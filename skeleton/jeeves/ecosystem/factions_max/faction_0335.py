"""Faction max 0335.
"""
from __future__ import annotations

ID = "faction_max_0335"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 335, "tier": 335 % 5}

def apply(context: str = "") -> dict:
    if not context and 335 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
