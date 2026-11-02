"""Item eco_supreme 1174.
"""
from __future__ import annotations

ID = "item_eco_supreme_1174"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1174, "tier": 1174 % 5}

def apply(context: str = "") -> dict:
    if not context and 1174 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
