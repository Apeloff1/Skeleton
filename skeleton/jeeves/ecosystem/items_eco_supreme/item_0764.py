"""Item eco_supreme 0764.
"""
from __future__ import annotations

ID = "item_eco_supreme_0764"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 764, "tier": 764 % 5}

def apply(context: str = "") -> dict:
    if not context and 764 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
