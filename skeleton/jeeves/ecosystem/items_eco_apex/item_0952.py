"""Item eco_apex 0952.
"""
from __future__ import annotations

ID = "item_eco_apex_0952"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 952, "tier": 952 % 5}

def apply(context: str = "") -> dict:
    if not context and 952 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
