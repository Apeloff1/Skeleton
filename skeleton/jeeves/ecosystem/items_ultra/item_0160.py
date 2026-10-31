"""Item ultra 0160.
"""
from __future__ import annotations

ID = "item_ultra_0160"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 160, "tier": 160 % 5}

def apply(context: str = "") -> dict:
    if not context and 160 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
