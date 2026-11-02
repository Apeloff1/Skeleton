"""Item eco_supreme 1128.
"""
from __future__ import annotations

ID = "item_eco_supreme_1128"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1128, "tier": 1128 % 5}

def apply(context: str = "") -> dict:
    if not context and 1128 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
