"""Item ultra 0307.
"""
from __future__ import annotations

ID = "item_ultra_0307"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 307, "tier": 307 % 5}

def apply(context: str = "") -> dict:
    if not context and 307 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
