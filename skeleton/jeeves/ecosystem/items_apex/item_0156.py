"""Item apex 0156.
"""
from __future__ import annotations

ID = "item_apex_0156"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 156, "tier": 156 % 5}

def apply(context: str = "") -> dict:
    if not context and 156 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
