"""Item ultimate 0882.
"""
from __future__ import annotations

ID = "item_ultimate_0882"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 882, "tier": 882 % 5}

def apply(context: str = "") -> dict:
    if not context and 882 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
