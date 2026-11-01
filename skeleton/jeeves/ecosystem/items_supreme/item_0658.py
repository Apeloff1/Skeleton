"""Item supreme 0658.
"""
from __future__ import annotations

ID = "item_supreme_0658"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 658, "tier": 658 % 5}

def apply(context: str = "") -> dict:
    if not context and 658 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
