"""Item ultimate 0593.
"""
from __future__ import annotations

ID = "item_ultimate_0593"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 593, "tier": 593 % 5}

def apply(context: str = "") -> dict:
    if not context and 593 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
