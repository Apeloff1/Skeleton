"""Item eco_peak 0774.
"""
from __future__ import annotations

ID = "item_eco_peak_0774"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 774, "tier": 774 % 5}

def apply(context: str = "") -> dict:
    if not context and 774 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
