"""Item eco_apex 0744.
"""
from __future__ import annotations

ID = "item_eco_apex_0744"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 744, "tier": 744 % 5}

def apply(context: str = "") -> dict:
    if not context and 744 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
