"""Item ultimate 0750.
"""
from __future__ import annotations

ID = "item_ultimate_0750"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 750, "tier": 750 % 5}

def apply(context: str = "") -> dict:
    if not context and 750 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
