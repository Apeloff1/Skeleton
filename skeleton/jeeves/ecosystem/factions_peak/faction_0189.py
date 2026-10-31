"""Faction peak 0189.
"""
from __future__ import annotations

ID = "faction_peak_0189"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 189, "tier": 189 % 5}

def apply(context: str = "") -> dict:
    if not context and 189 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
