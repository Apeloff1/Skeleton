"""Item eco_supreme 0411.
"""
from __future__ import annotations

ID = "item_eco_supreme_0411"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 411, "tier": 411 % 5}

def apply(context: str = "") -> dict:
    if not context and 411 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
