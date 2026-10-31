"""Item peak 0199.
"""
from __future__ import annotations

ID = "item_peak_0199"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 199, "tier": 199 % 5}

def apply(context: str = "") -> dict:
    if not context and 199 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
