"""Item eco_apex 0198.
"""
from __future__ import annotations

ID = "item_eco_apex_0198"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 198, "tier": 198 % 5}

def apply(context: str = "") -> dict:
    if not context and 198 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
