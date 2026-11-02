"""Item eco_apex 1006.
"""
from __future__ import annotations

ID = "item_eco_apex_1006"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1006, "tier": 1006 % 5}

def apply(context: str = "") -> dict:
    if not context and 1006 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
