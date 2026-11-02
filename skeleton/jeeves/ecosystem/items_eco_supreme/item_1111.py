"""Item eco_supreme 1111.
"""
from __future__ import annotations

ID = "item_eco_supreme_1111"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1111, "tier": 1111 % 5}

def apply(context: str = "") -> dict:
    if not context and 1111 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
