"""Item ultimate 0806.
"""
from __future__ import annotations

ID = "item_ultimate_0806"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 806, "tier": 806 % 5}

def apply(context: str = "") -> dict:
    if not context and 806 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
