"""Item eco_apex 0405.
"""
from __future__ import annotations

ID = "item_eco_apex_0405"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 405, "tier": 405 % 5}

def apply(context: str = "") -> dict:
    if not context and 405 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
