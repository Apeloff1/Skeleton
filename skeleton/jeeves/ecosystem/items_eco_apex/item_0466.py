"""Item eco_apex 0466.
"""
from __future__ import annotations

ID = "item_eco_apex_0466"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 466, "tier": 466 % 5}

def apply(context: str = "") -> dict:
    if not context and 466 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
