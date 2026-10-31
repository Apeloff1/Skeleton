"""Item apex 0485.
"""
from __future__ import annotations

ID = "item_apex_0485"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 485, "tier": 485 % 5}

def apply(context: str = "") -> dict:
    if not context and 485 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
