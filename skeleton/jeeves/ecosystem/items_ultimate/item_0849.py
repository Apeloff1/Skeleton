"""Item ultimate 0849.
"""
from __future__ import annotations

ID = "item_ultimate_0849"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 849, "tier": 849 % 5}

def apply(context: str = "") -> dict:
    if not context and 849 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
