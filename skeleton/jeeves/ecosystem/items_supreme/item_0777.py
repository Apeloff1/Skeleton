"""Item supreme 0777.
"""
from __future__ import annotations

ID = "item_supreme_0777"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 777, "tier": 777 % 5}

def apply(context: str = "") -> dict:
    if not context and 777 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
