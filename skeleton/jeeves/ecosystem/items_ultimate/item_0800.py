"""Item ultimate 0800.
"""
from __future__ import annotations

ID = "item_ultimate_0800"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 800, "tier": 800 % 5}

def apply(context: str = "") -> dict:
    if not context and 800 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
