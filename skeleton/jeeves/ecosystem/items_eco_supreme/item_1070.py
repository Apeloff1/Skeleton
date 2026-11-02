"""Item eco_supreme 1070.
"""
from __future__ import annotations

ID = "item_eco_supreme_1070"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1070, "tier": 1070 % 5}

def apply(context: str = "") -> dict:
    if not context and 1070 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
