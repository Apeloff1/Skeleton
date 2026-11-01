"""Item ultimate 0822.
"""
from __future__ import annotations

ID = "item_ultimate_0822"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 822, "tier": 822 % 5}

def apply(context: str = "") -> dict:
    if not context and 822 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
