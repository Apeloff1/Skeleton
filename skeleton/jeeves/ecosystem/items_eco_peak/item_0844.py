"""Item eco_peak 0844.
"""
from __future__ import annotations

ID = "item_eco_peak_0844"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 844, "tier": 844 % 5}

def apply(context: str = "") -> dict:
    if not context and 844 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
