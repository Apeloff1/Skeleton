"""Item max 0207.
"""
from __future__ import annotations

ID = "item_max_0207"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 207, "tier": 207 % 5}

def apply(context: str = "") -> dict:
    if not context and 207 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
