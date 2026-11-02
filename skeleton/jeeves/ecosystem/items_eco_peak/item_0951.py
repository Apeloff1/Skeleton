"""Item eco_peak 0951.
"""
from __future__ import annotations

ID = "item_eco_peak_0951"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 951, "tier": 951 % 5}

def apply(context: str = "") -> dict:
    if not context and 951 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
