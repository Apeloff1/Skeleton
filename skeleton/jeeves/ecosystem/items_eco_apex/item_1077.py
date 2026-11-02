"""Item eco_apex 1077.
"""
from __future__ import annotations

ID = "item_eco_apex_1077"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1077, "tier": 1077 % 5}

def apply(context: str = "") -> dict:
    if not context and 1077 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
