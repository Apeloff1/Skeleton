"""Item eco_supreme 0036.
"""
from __future__ import annotations

ID = "item_eco_supreme_0036"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 36, "tier": 36 % 5}

def apply(context: str = "") -> dict:
    if not context and 36 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
