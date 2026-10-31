"""Item ultra 0335.
"""
from __future__ import annotations

ID = "item_ultra_0335"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 335, "tier": 335 % 5}

def apply(context: str = "") -> dict:
    if not context and 335 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
