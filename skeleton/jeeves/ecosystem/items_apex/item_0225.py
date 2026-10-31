"""Item apex 0225.
"""
from __future__ import annotations

ID = "item_apex_0225"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 225, "tier": 225 % 5}

def apply(context: str = "") -> dict:
    if not context and 225 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
