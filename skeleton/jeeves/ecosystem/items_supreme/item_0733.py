"""Item supreme 0733.
"""
from __future__ import annotations

ID = "item_supreme_0733"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 733, "tier": 733 % 5}

def apply(context: str = "") -> dict:
    if not context and 733 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
