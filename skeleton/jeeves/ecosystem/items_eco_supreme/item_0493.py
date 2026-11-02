"""Item eco_supreme 0493.
"""
from __future__ import annotations

ID = "item_eco_supreme_0493"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 493, "tier": 493 % 5}

def apply(context: str = "") -> dict:
    if not context and 493 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
