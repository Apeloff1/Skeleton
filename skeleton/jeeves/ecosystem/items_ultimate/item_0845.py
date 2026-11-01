"""Item ultimate 0845.
"""
from __future__ import annotations

ID = "item_ultimate_0845"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 845, "tier": 845 % 5}

def apply(context: str = "") -> dict:
    if not context and 845 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
