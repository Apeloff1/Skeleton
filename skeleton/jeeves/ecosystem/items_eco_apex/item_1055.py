"""Item eco_apex 1055.
"""
from __future__ import annotations

ID = "item_eco_apex_1055"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1055, "tier": 1055 % 5}

def apply(context: str = "") -> dict:
    if not context and 1055 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
