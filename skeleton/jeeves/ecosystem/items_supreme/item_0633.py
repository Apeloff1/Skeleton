"""Item supreme 0633.
"""
from __future__ import annotations

ID = "item_supreme_0633"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 633, "tier": 633 % 5}

def apply(context: str = "") -> dict:
    if not context and 633 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
