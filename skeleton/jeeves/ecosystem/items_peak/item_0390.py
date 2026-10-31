"""Item peak 0390.
"""
from __future__ import annotations

ID = "item_peak_0390"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 390, "tier": 390 % 5}

def apply(context: str = "") -> dict:
    if not context and 390 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
