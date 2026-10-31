"""Item apex 0097.
"""
from __future__ import annotations

ID = "item_apex_0097"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 97, "tier": 97 % 5}

def apply(context: str = "") -> dict:
    if not context and 97 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
