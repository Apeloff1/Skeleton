"""Item ultra 0328.
"""
from __future__ import annotations

ID = "item_ultra_0328"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 328, "tier": 328 % 5}

def apply(context: str = "") -> dict:
    if not context and 328 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
