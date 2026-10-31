"""Item apex 0364.
"""
from __future__ import annotations

ID = "item_apex_0364"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 364, "tier": 364 % 5}

def apply(context: str = "") -> dict:
    if not context and 364 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
