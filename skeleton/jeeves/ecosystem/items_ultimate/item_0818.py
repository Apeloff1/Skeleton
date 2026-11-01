"""Item ultimate 0818.
"""
from __future__ import annotations

ID = "item_ultimate_0818"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 818, "tier": 818 % 5}

def apply(context: str = "") -> dict:
    if not context and 818 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
