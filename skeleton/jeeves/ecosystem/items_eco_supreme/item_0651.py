"""Item eco_supreme 0651.
"""
from __future__ import annotations

ID = "item_eco_supreme_0651"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 651, "tier": 651 % 5}

def apply(context: str = "") -> dict:
    if not context and 651 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
