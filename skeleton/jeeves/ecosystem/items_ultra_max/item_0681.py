"""Item ultra_max 0681.
"""
from __future__ import annotations

ID = "item_ultra_max_0681"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 681, "tier": 681 % 5}

def apply(context: str = "") -> dict:
    if not context and 681 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
