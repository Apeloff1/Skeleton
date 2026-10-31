"""Item peak 0080.
"""
from __future__ import annotations

ID = "item_peak_0080"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 80, "tier": 80 % 5}

def apply(context: str = "") -> dict:
    if not context and 80 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
