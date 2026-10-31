"""Item peak 0389.
"""
from __future__ import annotations

ID = "item_peak_0389"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 389, "tier": 389 % 5}

def apply(context: str = "") -> dict:
    if not context and 389 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
