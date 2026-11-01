"""Item supreme 0506.
"""
from __future__ import annotations

ID = "item_supreme_0506"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 506, "tier": 506 % 5}

def apply(context: str = "") -> dict:
    if not context and 506 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
