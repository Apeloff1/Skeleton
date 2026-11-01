"""Item ultimate 0581.
"""
from __future__ import annotations

ID = "item_ultimate_0581"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 581, "tier": 581 % 5}

def apply(context: str = "") -> dict:
    if not context and 581 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
