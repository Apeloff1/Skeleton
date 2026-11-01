"""Item ultimate 0266.
"""
from __future__ import annotations

ID = "item_ultimate_0266"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 266, "tier": 266 % 5}

def apply(context: str = "") -> dict:
    if not context and 266 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
