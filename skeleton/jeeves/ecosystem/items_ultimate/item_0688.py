"""Item ultimate 0688.
"""
from __future__ import annotations

ID = "item_ultimate_0688"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 688, "tier": 688 % 5}

def apply(context: str = "") -> dict:
    if not context and 688 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
