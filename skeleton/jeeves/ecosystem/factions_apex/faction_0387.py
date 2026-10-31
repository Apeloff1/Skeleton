"""Faction apex 0387.
"""
from __future__ import annotations

ID = "faction_apex_0387"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 387, "tier": 387 % 5}

def apply(context: str = "") -> dict:
    if not context and 387 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
