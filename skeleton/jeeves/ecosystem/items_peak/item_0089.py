"""Item peak 0089.
"""
from __future__ import annotations

ID = "item_peak_0089"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 89, "tier": 89 % 5}

def apply(context: str = "") -> dict:
    if not context and 89 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
