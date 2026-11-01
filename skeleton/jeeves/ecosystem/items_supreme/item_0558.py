"""Item supreme 0558.
"""
from __future__ import annotations

ID = "item_supreme_0558"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 558, "tier": 558 % 5}

def apply(context: str = "") -> dict:
    if not context and 558 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
