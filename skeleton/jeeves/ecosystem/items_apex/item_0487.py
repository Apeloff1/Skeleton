"""Item apex 0487.
"""
from __future__ import annotations

ID = "item_apex_0487"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 487, "tier": 487 % 5}

def apply(context: str = "") -> dict:
    if not context and 487 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
