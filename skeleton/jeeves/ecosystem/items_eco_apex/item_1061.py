"""Item eco_apex 1061.
"""
from __future__ import annotations

ID = "item_eco_apex_1061"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1061, "tier": 1061 % 5}

def apply(context: str = "") -> dict:
    if not context and 1061 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
