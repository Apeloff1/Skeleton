"""Item eco_apex 0312.
"""
from __future__ import annotations

ID = "item_eco_apex_0312"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 312, "tier": 312 % 5}

def apply(context: str = "") -> dict:
    if not context and 312 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
