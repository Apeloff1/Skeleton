"""Item supreme 0555.
"""
from __future__ import annotations

ID = "item_supreme_0555"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 555, "tier": 555 % 5}

def apply(context: str = "") -> dict:
    if not context and 555 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
