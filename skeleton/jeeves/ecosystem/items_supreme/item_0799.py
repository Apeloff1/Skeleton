"""Item supreme 0799.
"""
from __future__ import annotations

ID = "item_supreme_0799"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 799, "tier": 799 % 5}

def apply(context: str = "") -> dict:
    if not context and 799 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
