"""Item eco_apex 0048.
"""
from __future__ import annotations

ID = "item_eco_apex_0048"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 48, "tier": 48 % 5}

def apply(context: str = "") -> dict:
    if not context and 48 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
