"""Item eco_apex 1062.
"""
from __future__ import annotations

ID = "item_eco_apex_1062"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1062, "tier": 1062 % 5}

def apply(context: str = "") -> dict:
    if not context and 1062 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
