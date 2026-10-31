"""Item peak 0425.
"""
from __future__ import annotations

ID = "item_peak_0425"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 425, "tier": 425 % 5}

def apply(context: str = "") -> dict:
    if not context and 425 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
