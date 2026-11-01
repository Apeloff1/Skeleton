"""Item ultimate 0455.
"""
from __future__ import annotations

ID = "item_ultimate_0455"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 455, "tier": 455 % 5}

def apply(context: str = "") -> dict:
    if not context and 455 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
