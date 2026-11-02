"""Item eco_peak 0854.
"""
from __future__ import annotations

ID = "item_eco_peak_0854"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 854, "tier": 854 % 5}

def apply(context: str = "") -> dict:
    if not context and 854 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
