"""Item eco_supreme 1190.
"""
from __future__ import annotations

ID = "item_eco_supreme_1190"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1190, "tier": 1190 % 5}

def apply(context: str = "") -> dict:
    if not context and 1190 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
