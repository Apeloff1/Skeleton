"""Item eco_peak 0957.
"""
from __future__ import annotations

ID = "item_eco_peak_0957"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 957, "tier": 957 % 5}

def apply(context: str = "") -> dict:
    if not context and 957 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
