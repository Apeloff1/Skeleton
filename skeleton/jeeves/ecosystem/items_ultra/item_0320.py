"""Item ultra 0320.
"""
from __future__ import annotations

ID = "item_ultra_0320"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 320, "tier": 320 % 5}

def apply(context: str = "") -> dict:
    if not context and 320 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
