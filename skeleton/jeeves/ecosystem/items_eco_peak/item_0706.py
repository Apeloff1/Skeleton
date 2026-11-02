"""Item eco_peak 0706.
"""
from __future__ import annotations

ID = "item_eco_peak_0706"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 706, "tier": 706 % 5}

def apply(context: str = "") -> dict:
    if not context and 706 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
