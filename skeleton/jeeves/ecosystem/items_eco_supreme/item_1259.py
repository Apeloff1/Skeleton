"""Item eco_supreme 1259.
"""
from __future__ import annotations

ID = "item_eco_supreme_1259"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1259, "tier": 1259 % 5}

def apply(context: str = "") -> dict:
    if not context and 1259 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
