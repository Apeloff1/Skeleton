"""Faction apex 0327.
"""
from __future__ import annotations

ID = "faction_apex_0327"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 327, "tier": 327 % 5}

def apply(context: str = "") -> dict:
    if not context and 327 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
