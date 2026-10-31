"""Item peak 0414.
"""
from __future__ import annotations

ID = "item_peak_0414"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 414, "tier": 414 % 5}

def apply(context: str = "") -> dict:
    if not context and 414 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
