"""Item max 0201.
"""
from __future__ import annotations

ID = "item_max_0201"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 201, "tier": 201 % 5}

def apply(context: str = "") -> dict:
    if not context and 201 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
