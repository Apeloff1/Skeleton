"""Item ultimate 0737.
"""
from __future__ import annotations

ID = "item_ultimate_0737"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 737, "tier": 737 % 5}

def apply(context: str = "") -> dict:
    if not context and 737 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
