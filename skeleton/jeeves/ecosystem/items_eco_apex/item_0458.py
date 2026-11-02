"""Item eco_apex 0458.
"""
from __future__ import annotations

ID = "item_eco_apex_0458"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 458, "tier": 458 % 5}

def apply(context: str = "") -> dict:
    if not context and 458 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
