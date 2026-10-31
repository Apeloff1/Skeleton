"""Item peak 0350.
"""
from __future__ import annotations

ID = "item_peak_0350"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 350, "tier": 350 % 5}

def apply(context: str = "") -> dict:
    if not context and 350 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
