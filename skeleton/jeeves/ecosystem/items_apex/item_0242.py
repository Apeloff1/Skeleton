"""Item apex 0242.
"""
from __future__ import annotations

ID = "item_apex_0242"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 242, "tier": 242 % 5}

def apply(context: str = "") -> dict:
    if not context and 242 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
