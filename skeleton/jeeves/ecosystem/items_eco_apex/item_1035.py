"""Item eco_apex 1035.
"""
from __future__ import annotations

ID = "item_eco_apex_1035"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1035, "tier": 1035 % 5}

def apply(context: str = "") -> dict:
    if not context and 1035 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
