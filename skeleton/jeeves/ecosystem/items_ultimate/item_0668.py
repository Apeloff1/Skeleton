"""Item ultimate 0668.
"""
from __future__ import annotations

ID = "item_ultimate_0668"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 668, "tier": 668 % 5}

def apply(context: str = "") -> dict:
    if not context and 668 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
