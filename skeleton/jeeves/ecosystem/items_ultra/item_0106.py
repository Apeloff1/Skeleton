"""Item ultra 0106.
"""
from __future__ import annotations

ID = "item_ultra_0106"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 106, "tier": 106 % 5}

def apply(context: str = "") -> dict:
    if not context and 106 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
