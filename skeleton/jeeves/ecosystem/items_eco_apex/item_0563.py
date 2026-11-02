"""Item eco_apex 0563.
"""
from __future__ import annotations

ID = "item_eco_apex_0563"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 563, "tier": 563 % 5}

def apply(context: str = "") -> dict:
    if not context and 563 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
