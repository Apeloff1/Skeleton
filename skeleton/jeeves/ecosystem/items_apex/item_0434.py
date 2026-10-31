"""Item apex 0434.
"""
from __future__ import annotations

ID = "item_apex_0434"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 434, "tier": 434 % 5}

def apply(context: str = "") -> dict:
    if not context and 434 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
