"""Item peak 0391.
"""
from __future__ import annotations

ID = "item_peak_0391"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 391, "tier": 391 % 5}

def apply(context: str = "") -> dict:
    if not context and 391 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
