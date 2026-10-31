"""Item apex 0412.
"""
from __future__ import annotations

ID = "item_apex_0412"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 412, "tier": 412 % 5}

def apply(context: str = "") -> dict:
    if not context and 412 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
