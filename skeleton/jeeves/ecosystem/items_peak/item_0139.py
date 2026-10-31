"""Item peak 0139.
"""
from __future__ import annotations

ID = "item_peak_0139"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 139, "tier": 139 % 5}

def apply(context: str = "") -> dict:
    if not context and 139 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
