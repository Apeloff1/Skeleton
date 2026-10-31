"""Item peak 0419.
"""
from __future__ import annotations

ID = "item_peak_0419"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 419, "tier": 419 % 5}

def apply(context: str = "") -> dict:
    if not context and 419 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
