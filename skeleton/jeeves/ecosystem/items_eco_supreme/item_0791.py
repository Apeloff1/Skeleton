"""Item eco_supreme 0791.
"""
from __future__ import annotations

ID = "item_eco_supreme_0791"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 791, "tier": 791 % 5}

def apply(context: str = "") -> dict:
    if not context and 791 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
