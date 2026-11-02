"""Item eco_apex 1016.
"""
from __future__ import annotations

ID = "item_eco_apex_1016"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1016, "tier": 1016 % 5}

def apply(context: str = "") -> dict:
    if not context and 1016 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
