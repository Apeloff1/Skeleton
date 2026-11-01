"""Item ultra_max 0031.
"""
from __future__ import annotations

ID = "item_ultra_max_0031"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 31, "tier": 31 % 5}

def apply(context: str = "") -> dict:
    if not context and 31 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
