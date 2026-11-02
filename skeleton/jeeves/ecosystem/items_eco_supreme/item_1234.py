"""Item eco_supreme 1234.
"""
from __future__ import annotations

ID = "item_eco_supreme_1234"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1234, "tier": 1234 % 5}

def apply(context: str = "") -> dict:
    if not context and 1234 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
