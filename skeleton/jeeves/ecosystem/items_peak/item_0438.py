"""Item peak 0438.
"""
from __future__ import annotations

ID = "item_peak_0438"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 438, "tier": 438 % 5}

def apply(context: str = "") -> dict:
    if not context and 438 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
