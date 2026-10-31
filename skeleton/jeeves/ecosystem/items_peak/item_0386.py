"""Item peak 0386.
"""
from __future__ import annotations

ID = "item_peak_0386"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 386, "tier": 386 % 5}

def apply(context: str = "") -> dict:
    if not context and 386 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
