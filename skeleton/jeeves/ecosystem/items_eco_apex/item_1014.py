"""Item eco_apex 1014.
"""
from __future__ import annotations

ID = "item_eco_apex_1014"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1014, "tier": 1014 % 5}

def apply(context: str = "") -> dict:
    if not context and 1014 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
