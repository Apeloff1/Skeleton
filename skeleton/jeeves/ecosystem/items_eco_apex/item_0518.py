"""Item eco_apex 0518.
"""
from __future__ import annotations

ID = "item_eco_apex_0518"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 518, "tier": 518 % 5}

def apply(context: str = "") -> dict:
    if not context and 518 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
