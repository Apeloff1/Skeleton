"""Item supreme 0090.
"""
from __future__ import annotations

ID = "item_supreme_0090"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 90, "tier": 90 % 5}

def apply(context: str = "") -> dict:
    if not context and 90 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
