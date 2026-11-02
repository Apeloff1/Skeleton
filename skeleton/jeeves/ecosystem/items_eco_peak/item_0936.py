"""Item eco_peak 0936.
"""
from __future__ import annotations

ID = "item_eco_peak_0936"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 936, "tier": 936 % 5}

def apply(context: str = "") -> dict:
    if not context and 936 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
