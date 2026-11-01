"""Item ultimate 0761.
"""
from __future__ import annotations

ID = "item_ultimate_0761"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 761, "tier": 761 % 5}

def apply(context: str = "") -> dict:
    if not context and 761 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
