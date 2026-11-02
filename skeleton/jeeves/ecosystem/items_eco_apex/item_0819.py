"""Item eco_apex 0819.
"""
from __future__ import annotations

ID = "item_eco_apex_0819"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 819, "tier": 819 % 5}

def apply(context: str = "") -> dict:
    if not context and 819 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
