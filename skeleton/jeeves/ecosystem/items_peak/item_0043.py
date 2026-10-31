"""Item peak 0043.
"""
from __future__ import annotations

ID = "item_peak_0043"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 43, "tier": 43 % 5}

def apply(context: str = "") -> dict:
    if not context and 43 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
