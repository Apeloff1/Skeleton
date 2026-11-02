"""Item eco_peak 0781.
"""
from __future__ import annotations

ID = "item_eco_peak_0781"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 781, "tier": 781 % 5}

def apply(context: str = "") -> dict:
    if not context and 781 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
