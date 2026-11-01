"""Faction supreme 0646.
"""
from __future__ import annotations

ID = "faction_supreme_0646"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 646, "tier": 646 % 5}

def apply(context: str = "") -> dict:
    if not context and 646 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
