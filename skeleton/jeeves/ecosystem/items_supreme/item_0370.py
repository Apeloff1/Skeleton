"""Item supreme 0370.
"""
from __future__ import annotations

ID = "item_supreme_0370"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 370, "tier": 370 % 5}

def apply(context: str = "") -> dict:
    if not context and 370 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
