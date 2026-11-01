"""Item supreme 0700.
"""
from __future__ import annotations

ID = "item_supreme_0700"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 700, "tier": 700 % 5}

def apply(context: str = "") -> dict:
    if not context and 700 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
