"""Item peak 0092.
"""
from __future__ import annotations

ID = "item_peak_0092"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 92, "tier": 92 % 5}

def apply(context: str = "") -> dict:
    if not context and 92 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
