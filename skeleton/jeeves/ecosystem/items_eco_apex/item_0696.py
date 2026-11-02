"""Item eco_apex 0696.
"""
from __future__ import annotations

ID = "item_eco_apex_0696"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 696, "tier": 696 % 5}

def apply(context: str = "") -> dict:
    if not context and 696 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
