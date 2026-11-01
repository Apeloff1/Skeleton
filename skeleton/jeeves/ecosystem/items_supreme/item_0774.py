"""Item supreme 0774.
"""
from __future__ import annotations

ID = "item_supreme_0774"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 774, "tier": 774 % 5}

def apply(context: str = "") -> dict:
    if not context and 774 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
