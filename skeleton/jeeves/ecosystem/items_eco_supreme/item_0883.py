"""Item eco_supreme 0883.
"""
from __future__ import annotations

ID = "item_eco_supreme_0883"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 883, "tier": 883 % 5}

def apply(context: str = "") -> dict:
    if not context and 883 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
