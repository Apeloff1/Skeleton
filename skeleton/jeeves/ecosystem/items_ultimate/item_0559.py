"""Item ultimate 0559.
"""
from __future__ import annotations

ID = "item_ultimate_0559"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 559, "tier": 559 % 5}

def apply(context: str = "") -> dict:
    if not context and 559 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
