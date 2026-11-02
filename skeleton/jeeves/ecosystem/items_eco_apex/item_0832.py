"""Item eco_apex 0832.
"""
from __future__ import annotations

ID = "item_eco_apex_0832"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 832, "tier": 832 % 5}

def apply(context: str = "") -> dict:
    if not context and 832 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
