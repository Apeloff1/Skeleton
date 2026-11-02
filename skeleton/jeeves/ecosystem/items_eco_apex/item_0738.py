"""Item eco_apex 0738.
"""
from __future__ import annotations

ID = "item_eco_apex_0738"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 738, "tier": 738 % 5}

def apply(context: str = "") -> dict:
    if not context and 738 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
