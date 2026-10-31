"""Item peak 0436.
"""
from __future__ import annotations

ID = "item_peak_0436"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 436, "tier": 436 % 5}

def apply(context: str = "") -> dict:
    if not context and 436 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
