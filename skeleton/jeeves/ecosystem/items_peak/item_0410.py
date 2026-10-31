"""Item peak 0410.
"""
from __future__ import annotations

ID = "item_peak_0410"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 410, "tier": 410 % 5}

def apply(context: str = "") -> dict:
    if not context and 410 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
