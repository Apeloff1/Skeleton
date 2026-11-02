"""Item eco_apex 1086.
"""
from __future__ import annotations

ID = "item_eco_apex_1086"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1086, "tier": 1086 % 5}

def apply(context: str = "") -> dict:
    if not context and 1086 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
