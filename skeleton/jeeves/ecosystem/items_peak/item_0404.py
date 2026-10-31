"""Item peak 0404.
"""
from __future__ import annotations

ID = "item_peak_0404"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 404, "tier": 404 % 5}

def apply(context: str = "") -> dict:
    if not context and 404 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
