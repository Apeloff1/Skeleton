"""Item peak 0430.
"""
from __future__ import annotations

ID = "item_peak_0430"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 430, "tier": 430 % 5}

def apply(context: str = "") -> dict:
    if not context and 430 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
