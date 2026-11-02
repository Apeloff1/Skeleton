"""Item eco_apex 0959.
"""
from __future__ import annotations

ID = "item_eco_apex_0959"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 959, "tier": 959 % 5}

def apply(context: str = "") -> dict:
    if not context and 959 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
