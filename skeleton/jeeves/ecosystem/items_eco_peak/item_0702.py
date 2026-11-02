"""Item eco_peak 0702.
"""
from __future__ import annotations

ID = "item_eco_peak_0702"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 702, "tier": 702 % 5}

def apply(context: str = "") -> dict:
    if not context and 702 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
