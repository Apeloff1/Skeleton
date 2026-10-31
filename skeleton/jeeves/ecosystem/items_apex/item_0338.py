"""Item apex 0338.
"""
from __future__ import annotations

ID = "item_apex_0338"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 338, "tier": 338 % 5}

def apply(context: str = "") -> dict:
    if not context and 338 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
