"""Item supreme 0709.
"""
from __future__ import annotations

ID = "item_supreme_0709"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 709, "tier": 709 % 5}

def apply(context: str = "") -> dict:
    if not context and 709 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
