"""Item ultra_max 0567.
"""
from __future__ import annotations

ID = "item_ultra_max_0567"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 567, "tier": 567 % 5}

def apply(context: str = "") -> dict:
    if not context and 567 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
