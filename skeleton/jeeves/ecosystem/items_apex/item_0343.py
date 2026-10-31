"""Item apex 0343.
"""
from __future__ import annotations

ID = "item_apex_0343"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 343, "tier": 343 % 5}

def apply(context: str = "") -> dict:
    if not context and 343 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
