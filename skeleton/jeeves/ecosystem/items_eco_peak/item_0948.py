"""Item eco_peak 0948.
"""
from __future__ import annotations

ID = "item_eco_peak_0948"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 948, "tier": 948 % 5}

def apply(context: str = "") -> dict:
    if not context and 948 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
