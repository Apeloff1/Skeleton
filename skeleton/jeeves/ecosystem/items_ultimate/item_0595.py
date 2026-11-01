"""Item ultimate 0595.
"""
from __future__ import annotations

ID = "item_ultimate_0595"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 595, "tier": 595 % 5}

def apply(context: str = "") -> dict:
    if not context and 595 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
