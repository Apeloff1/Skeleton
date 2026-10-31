"""Item max 0319.
"""
from __future__ import annotations

ID = "item_max_0319"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 319, "tier": 319 % 5}

def apply(context: str = "") -> dict:
    if not context and 319 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
