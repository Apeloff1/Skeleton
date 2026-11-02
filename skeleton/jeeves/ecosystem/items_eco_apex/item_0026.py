"""Item eco_apex 0026.
"""
from __future__ import annotations

ID = "item_eco_apex_0026"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 26, "tier": 26 % 5}

def apply(context: str = "") -> dict:
    if not context and 26 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
