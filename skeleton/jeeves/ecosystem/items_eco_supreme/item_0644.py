"""Item eco_supreme 0644.
"""
from __future__ import annotations

ID = "item_eco_supreme_0644"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 644, "tier": 644 % 5}

def apply(context: str = "") -> dict:
    if not context and 644 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
