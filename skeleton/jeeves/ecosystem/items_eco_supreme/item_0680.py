"""Item eco_supreme 0680.
"""
from __future__ import annotations

ID = "item_eco_supreme_0680"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 680, "tier": 680 % 5}

def apply(context: str = "") -> dict:
    if not context and 680 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
