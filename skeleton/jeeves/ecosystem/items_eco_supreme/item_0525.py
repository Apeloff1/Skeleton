"""Item eco_supreme 0525.
"""
from __future__ import annotations

ID = "item_eco_supreme_0525"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 525, "tier": 525 % 5}

def apply(context: str = "") -> dict:
    if not context and 525 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
