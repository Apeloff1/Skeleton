"""Item max 0374.
"""
from __future__ import annotations

ID = "item_max_0374"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 374, "tier": 374 % 5}

def apply(context: str = "") -> dict:
    if not context and 374 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
