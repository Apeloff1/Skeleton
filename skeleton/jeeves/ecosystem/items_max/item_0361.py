"""Item max 0361.
"""
from __future__ import annotations

ID = "item_max_0361"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 361, "tier": 361 % 5}

def apply(context: str = "") -> dict:
    if not context and 361 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
