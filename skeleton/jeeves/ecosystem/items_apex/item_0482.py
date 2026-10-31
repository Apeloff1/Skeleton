"""Item apex 0482.
"""
from __future__ import annotations

ID = "item_apex_0482"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 482, "tier": 482 % 5}

def apply(context: str = "") -> dict:
    if not context and 482 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
