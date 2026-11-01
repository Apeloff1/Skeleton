"""Item ultimate 0704.
"""
from __future__ import annotations

ID = "item_ultimate_0704"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 704, "tier": 704 % 5}

def apply(context: str = "") -> dict:
    if not context and 704 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
