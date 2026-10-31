"""Item peak 0368.
"""
from __future__ import annotations

ID = "item_peak_0368"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 368, "tier": 368 % 5}

def apply(context: str = "") -> dict:
    if not context and 368 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
