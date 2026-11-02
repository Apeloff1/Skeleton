"""Item eco_apex 1059.
"""
from __future__ import annotations

ID = "item_eco_apex_1059"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1059, "tier": 1059 % 5}

def apply(context: str = "") -> dict:
    if not context and 1059 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
