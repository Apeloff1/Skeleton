"""Item eco_apex 0624.
"""
from __future__ import annotations

ID = "item_eco_apex_0624"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 624, "tier": 624 % 5}

def apply(context: str = "") -> dict:
    if not context and 624 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
