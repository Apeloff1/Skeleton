"""Item peak 0283.
"""
from __future__ import annotations

ID = "item_peak_0283"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 283, "tier": 283 % 5}

def apply(context: str = "") -> dict:
    if not context and 283 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
