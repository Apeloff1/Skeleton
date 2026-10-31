"""Item apex 0449.
"""
from __future__ import annotations

ID = "item_apex_0449"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 449, "tier": 449 % 5}

def apply(context: str = "") -> dict:
    if not context and 449 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
