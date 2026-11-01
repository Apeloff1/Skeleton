"""Item ultimate 0745.
"""
from __future__ import annotations

ID = "item_ultimate_0745"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 745, "tier": 745 % 5}

def apply(context: str = "") -> dict:
    if not context and 745 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
