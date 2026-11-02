"""Item eco_supreme 1296.
"""
from __future__ import annotations

ID = "item_eco_supreme_1296"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1296, "tier": 1296 % 5}

def apply(context: str = "") -> dict:
    if not context and 1296 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
