"""Item apex 0478.
"""
from __future__ import annotations

ID = "item_apex_0478"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 478, "tier": 478 % 5}

def apply(context: str = "") -> dict:
    if not context and 478 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
