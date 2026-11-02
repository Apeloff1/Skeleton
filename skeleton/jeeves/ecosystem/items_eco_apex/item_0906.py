"""Item eco_apex 0906.
"""
from __future__ import annotations

ID = "item_eco_apex_0906"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 906, "tier": 906 % 5}

def apply(context: str = "") -> dict:
    if not context and 906 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
