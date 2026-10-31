"""Item peak 0205.
"""
from __future__ import annotations

ID = "item_peak_0205"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 205, "tier": 205 % 5}

def apply(context: str = "") -> dict:
    if not context and 205 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
