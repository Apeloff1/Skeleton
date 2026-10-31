"""Item peak 0413.
"""
from __future__ import annotations

ID = "item_peak_0413"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 413, "tier": 413 % 5}

def apply(context: str = "") -> dict:
    if not context and 413 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
