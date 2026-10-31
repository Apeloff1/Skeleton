"""Item peak 0354.
"""
from __future__ import annotations

ID = "item_peak_0354"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 354, "tier": 354 % 5}

def apply(context: str = "") -> dict:
    if not context and 354 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
