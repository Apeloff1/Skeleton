"""Item eco_apex 1084.
"""
from __future__ import annotations

ID = "item_eco_apex_1084"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1084, "tier": 1084 % 5}

def apply(context: str = "") -> dict:
    if not context and 1084 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
