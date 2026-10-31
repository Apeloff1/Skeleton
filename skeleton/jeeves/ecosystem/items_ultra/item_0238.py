"""Item ultra 0238.
"""
from __future__ import annotations

ID = "item_ultra_0238"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 238, "tier": 238 % 5}

def apply(context: str = "") -> dict:
    if not context and 238 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
