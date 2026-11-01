"""Item supreme 0514.
"""
from __future__ import annotations

ID = "item_supreme_0514"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 514, "tier": 514 % 5}

def apply(context: str = "") -> dict:
    if not context and 514 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
