"""Item eco_supreme 0763.
"""
from __future__ import annotations

ID = "item_eco_supreme_0763"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 763, "tier": 763 % 5}

def apply(context: str = "") -> dict:
    if not context and 763 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
