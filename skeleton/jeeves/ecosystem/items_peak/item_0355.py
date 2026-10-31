"""Item peak 0355.
"""
from __future__ import annotations

ID = "item_peak_0355"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 355, "tier": 355 % 5}

def apply(context: str = "") -> dict:
    if not context and 355 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
